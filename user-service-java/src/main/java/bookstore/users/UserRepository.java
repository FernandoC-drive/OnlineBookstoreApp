package bookstore.users;

import com.mysql.cj.jdbc.MysqlDataSource;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;

final class UserRepository implements AutoCloseable {
    record LoginUser(int id, String username, String email, String role, String passwordHash) {}

    record Profile(int userId, String username, String email, String role, String createdAt) {}

    private final HikariDataSource dataSource;

    UserRepository(Config config) throws SQLException {
        var mysql = new MysqlDataSource();
        mysql.setServerName(config.mysqlHost());
        mysql.setPortNumber(config.mysqlPort());
        mysql.setUser(config.mysqlUser());
        mysql.setPassword(config.mysqlPassword());
        mysql.setDatabaseName(config.mysqlDatabase());
        mysql.setConnectTimeout(3000);
        mysql.setSocketTimeout(3000);
        mysql.setServerTimezone("+00:00");
        mysql.setForceConnectionTimeZoneToSession(true);

        var pool = new HikariConfig();
        pool.setDataSource(mysql);
        pool.setMaximumPoolSize(6);
        pool.setConnectionTimeout(3000);
        pool.setValidationTimeout(1500);
        dataSource = new HikariDataSource(pool);
    }

    @Override
    public void close() {
        dataSource.close();
    }

    int createCustomer(String username, String email, String passwordHash) throws SQLException {
        String sql = "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, 'CUSTOMER')";
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            statement.setString(1, username);
            statement.setString(2, email);
            statement.setString(3, passwordHash);
            statement.executeUpdate();

            try (var keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("MySQL did not return the new user's ID.");
                }
                return keys.getInt(1);
            }
        }
    }

    LoginUser findLoginUser(String username) throws SQLException {
        String sql = "SELECT id, username, email, role, password_hash FROM users WHERE username = ?";
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql)) {
            statement.setString(1, username);
            try (var rows = statement.executeQuery()) {
                if (rows.next()) {
                    return new LoginUser(rows.getInt("id"), rows.getString("username"),
                            rows.getString("email"), rows.getString("role"), rows.getString("password_hash"));
                }
                return null;
            }
        }
    }

    void createSession(String token, LoginUser user) throws SQLException {
        String sql = "INSERT INTO sessions (token, user_id, role) VALUES (?, ?, ?)";
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql)) {
            statement.setString(1, token);
            statement.setInt(2, user.id());
            statement.setString(3, user.role());
            statement.executeUpdate();
        }
    }

    boolean deleteSession(String token) throws SQLException {
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement("DELETE FROM sessions WHERE token = ?")) {
            statement.setString(1, token);
            return statement.executeUpdate() == 1;
        }
    }

    Profile findProfile(String token) throws SQLException {
        String sql = """
                SELECT u.id, u.username, u.email, s.role, u.created_at
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """;
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql)) {
            statement.setString(1, token);
            try (var rows = statement.executeQuery()) {
                if (rows.next()) {
                    Timestamp createdAt = rows.getTimestamp("created_at");
                    return new Profile(rows.getInt("id"), rows.getString("username"), rows.getString("email"),
                            rows.getString("role"), createdAt == null ? null : createdAt.toInstant().toString());
                }
                return null;
            }
        }
    }
}
