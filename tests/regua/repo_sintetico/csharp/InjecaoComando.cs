using System.Diagnostics;
using Microsoft.AspNetCore.Mvc;

public class PingController : Controller
{
    public IActionResult Ping(string host)
    {
        Process.Start("cmd.exe", "/c ping " + host);
        return Ok();
    }
}
