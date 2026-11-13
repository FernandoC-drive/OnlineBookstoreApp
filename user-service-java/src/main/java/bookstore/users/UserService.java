package bookstore.users;

import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonSyntaxException;
import com.google.gson.Strictness;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.mindrot.jbcrypt.BCrypt;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public final class UserService {
    private static final System.Logger LOGGER = System.getLogger(UserService.class.getName());
    private static final Gson JSON = new GsonBuilder()
            .setStrictness(Strictness.STRICT)
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .serializeNulls()
            .create();
    private static final int MAX_JSON_BYTES = 16 * 1024;
    private static final int MYSQL_DUPLICATE_KEY = 1062;
    private static final String EMAIL_ATOM = "[A-Za-z0-9!#$%&'*+/=?^_\\x60{|}~-]+";
    private static final Pattern EMAIL = Pattern.compile(
            EMAIL_ATOM + "(?:\\." + EMAIL_ATOM + ")*@"
            + "(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\\.)+[A-Za-z]{2,63}"
    );
    private static final Pattern BCRYPT_HASH = Pattern.compile(
            "\\$2[ab]\\$(?:0[4-9]|[12][0-9]|30)\\$[./A-Za-z0-9]{53}"
    );
    private static final Pattern BEARER = Pattern.compile(
            "(?i:Bearer) +([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    );

    private final UserRepository users;

    private UserService(UserRepository users) {
        this.users = users;
    }

    public static void main(String[] args) throws IOException, SQLException {
        Config config = Config.load();
        UserRepository users = new UserRepository(config);
        // Initialize the login query, bcrypt, and JSON serialization before serving requests.
        users.findLoginUser("");
        BCrypt.hashpw("startup", BCrypt.gensalt(10));
        JSON.toJson(new LoginResponse(UUID.randomUUID().toString(), 0, "", "", "CUSTOMER"));

        UserService service = new UserService(users);
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", config.servicePort()), 0);
        service.addRoute(server, "/api/users/register", "POST", service::register);
        service.addRoute(server, "/api/users/login", "POST", service::login);
        service.addRoute(server, "/api/users/logout", "POST", service::logout);
        service.addRoute(server, "/api/users/profile", "GET", service::profile);

        var executor = Executors.newCachedThreadPool();
        server.setExecutor(executor);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(0);
            executor.shutdown();
            users.close();
        }));
        server.start();
        System.out.printf("User service listening on http://127.0.0.1:%d%n", config.servicePort());
    }

    private void addRoute(HttpServer server, String path, String method, Route route) {
        server.createContext(path, exchange -> {
            try (exchange) {
                if (!path.equals(exchange.getRequestURI().getRawPath())) {
                    error(exchange, 404, "Endpoint not found");
                    return;
                }
                if (!method.equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", method);
                    error(exchange, 405, "Method not allowed");
                    return;
                }
                try {
                    route.handle(exchange);
                } catch (JsonParseException exception) {
                    error(exchange, 400, "Expected a JSON object");
                } catch (SQLException exception) {
                    LOGGER.log(System.Logger.Level.ERROR, "Database request failed", exception);
                    error(exchange, 500, "Database request failed");
                }
            }
        });
    }

    private void register(HttpExchange exchange) throws IOException, SQLException {
        JsonObject request = readJson(exchange);
        String username = stringField(request, "username").strip();
        String email = stringField(request, "email").strip();
        String password = stringField(request, "password");
        if (!validUsername(username) || !validPassword(password)
                || email.length() > 255 || email.indexOf('@') > 64 || !EMAIL.matcher(email).matches()) {
            error(exchange, 400, "Provide a username of 1–100 characters, a valid email, "
                    + "and a non-blank password of at most 72 UTF-8 bytes");
            return;
        }

        int userId;
        try {
            userId = users.createCustomer(username, email, BCrypt.hashpw(password, BCrypt.gensalt(10)));
        } catch (SQLException exception) {
            if (exception.getErrorCode() != MYSQL_DUPLICATE_KEY) {
                throw exception;
            }
            error(exchange, 409, "Username or email already exists");
            return;
        }
        respond(exchange, 201, Map.of("message", "User registered successfully", "user_id", userId));
    }

    private void login(HttpExchange exchange) throws IOException, SQLException {
        JsonObject request = readJson(exchange);
        String username = stringField(request, "username").strip();
        String password = stringField(request, "password");
        if (!validUsername(username) || !validPassword(password)) {
            error(exchange, 401, "Invalid username or password");
            return;
        }

        UserRepository.LoginUser user = users.findLoginUser(username);
        if (user == null || !passwordMatches(password, user.passwordHash())) {
            error(exchange, 401, "Invalid username or password");
            return;
        }

        String token = UUID.randomUUID().toString();
        users.createSession(token, user);
        respond(exchange, 200, new LoginResponse(token, user.id(), user.username(), user.email(), user.role()));
    }

    private void logout(HttpExchange exchange) throws IOException, SQLException {
        String token = bearerToken(exchange);
        if (token == null || !users.deleteSession(token)) {
            unauthorized(exchange);
            return;
        }
        respond(exchange, 200, Map.of("message", "Logged out successfully"));
    }

    private void profile(HttpExchange exchange) throws IOException, SQLException {
        String token = bearerToken(exchange);
        UserRepository.Profile profile = token == null ? null : users.findProfile(token);
        if (profile == null) {
            unauthorized(exchange);
            return;
        }
        respond(exchange, 200, profile);
    }

    private static JsonObject readJson(HttpExchange exchange) throws IOException {
        byte[] body = exchange.getRequestBody().readNBytes(MAX_JSON_BYTES + 1);
        if (body.length > MAX_JSON_BYTES) {
            throw new JsonSyntaxException("Request body is too large");
        }
        try {
            JsonObject object = JSON.fromJson(StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(body))
                    .toString(), JsonObject.class);
            if (object != null) {
                return object;
            }
        } catch (CharacterCodingException exception) {
            throw new JsonSyntaxException(exception);
        }
        throw new JsonSyntaxException("Expected a JSON object");
    }

    private static String stringField(JsonObject object, String name) {
        var value = object.get(name);
        return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()
                ? value.getAsString() : "";
    }

    private static boolean validUsername(String username) {
        return !username.isBlank() && username.codePointCount(0, username.length()) <= 100;
    }

    private static boolean validPassword(String password) {
        return !password.isBlank() && password.getBytes(StandardCharsets.UTF_8).length <= 72;
    }

    private static boolean passwordMatches(String password, String hash) {
        if (!BCRYPT_HASH.matcher(hash).matches()) {
            return false;
        }
        // jBCrypt accepts $2a$ but can verify the same bcrypt payload from $2b$.
        String compatibleHash = hash.startsWith("$2b$") ? "$2a$" + hash.substring(4) : hash;
        try {
            return BCrypt.checkpw(password, compatibleHash);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static String bearerToken(HttpExchange exchange) {
        var headers = exchange.getRequestHeaders().get("Authorization");
        if (headers == null || headers.size() != 1) {
            return null;
        }
        var match = BEARER.matcher(headers.get(0).strip());
        return match.matches() ? match.group(1) : null;
    }

    private static void unauthorized(HttpExchange exchange) throws IOException {
        exchange.getResponseHeaders().set("WWW-Authenticate", "Bearer");
        error(exchange, 401, "Invalid or missing session token");
    }

    private static void error(HttpExchange exchange, int status, String message) throws IOException {
        respond(exchange, status, Map.of("message", message));
    }

    private static void respond(HttpExchange exchange, int status, Object payload) throws IOException {
        byte[] body = JSON.toJson(payload).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
    }

    private record LoginResponse(String token, int userId, String username, String email, String role) {}

    @FunctionalInterface
    private interface Route {
        void handle(HttpExchange exchange) throws IOException, SQLException;
    }
}
