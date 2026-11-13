package bookstore.users;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

record Config(
        String mysqlHost, int mysqlPort, String mysqlUser, String mysqlPassword,
        String mysqlDatabase, int servicePort
) {
    private static final Pattern ENV_ENTRY = Pattern.compile(
            "(?:export\\s+)?([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*"
            + "(?:\"([^\"]*)\"\\s*(?:#.*)?|'([^']*)'\\s*(?:#.*)?|(.*?)(?:\\s+#.*)?)"
    );

    static Config load() throws IOException {
        Path local = Path.of(".env");
        Path envFile = Files.isRegularFile(local) ? local : Path.of("..", ".env");
        Map<String, String> values = new HashMap<>();
        if (Files.isRegularFile(envFile)) {
            for (String line : Files.readAllLines(envFile)) {
                var entry = ENV_ENTRY.matcher(line.strip());
                if (entry.matches()) {
                    String value = entry.group(2);
                    if (value == null) {
                        value = entry.group(3);
                    }
                    if (value == null) {
                        value = entry.group(4).strip();
                    }
                    values.put(entry.group(1), value);
                }
            }
        }
        values.putAll(System.getenv());

        return new Config(
                values.getOrDefault("MYSQL_HOST", "127.0.0.1"),
                port(values, "MYSQL_PORT", "3306"),
                values.getOrDefault("MYSQL_USER", "root"),
                values.getOrDefault("MYSQL_PASSWORD", ""),
                values.getOrDefault("MYSQL_DATABASE", "bookstore_db"),
                port(values, "USER_SERVICE_PORT", "8001")
        );
    }

    private static int port(Map<String, String> values, String key, String fallback) {
        try {
            int port = Integer.parseInt(values.getOrDefault(key, fallback));
            if (port >= 1 && port <= 65535) {
                return port;
            }
        } catch (NumberFormatException ignored) {
            // Report invalid numbers and out-of-range ports the same way.
        }
        throw new IllegalArgumentException(key + " must be a port number between 1 and 65535.");
    }
}
