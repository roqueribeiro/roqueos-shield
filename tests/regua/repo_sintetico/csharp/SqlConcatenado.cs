using System.Data.SqlClient;
using Microsoft.AspNetCore.Mvc;

public class ContasController : Controller
{
    private readonly SqlConnection conexao;

    public ContasController(SqlConnection c) { conexao = c; }

    public IActionResult Busca(string id)
    {
        var cmd = new SqlCommand("SELECT * FROM Contas WHERE Id = '" + id + "'", conexao);
        return Ok(cmd.ExecuteScalar());
    }
}
