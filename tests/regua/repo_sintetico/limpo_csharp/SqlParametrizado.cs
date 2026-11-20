using System.Data.SqlClient;

public class ContasSeguras
{
    public object Busca(SqlConnection conexao, string id)
    {
        var cmd = new SqlCommand("SELECT * FROM Contas WHERE Id = @id", conexao);
        cmd.Parameters.AddWithValue("@id", id);
        return cmd.ExecuteScalar();
    }
}
