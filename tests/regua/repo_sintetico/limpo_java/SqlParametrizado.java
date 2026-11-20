import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class SqlParametrizado {
    public boolean existe(Connection conn, String id) throws SQLException {
        PreparedStatement ps = conn.prepareStatement("SELECT 1 FROM contas WHERE id = ?");
        ps.setString(1, id);
        ResultSet rs = ps.executeQuery();
        return rs.next();
    }
}
