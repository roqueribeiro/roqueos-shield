using System.IO;
using System.Runtime.Serialization.Formatters.Binary;

public class Desserializa
{
    public object Ler(Stream entrada)
    {
        var bf = new BinaryFormatter();
        return bf.Deserialize(entrada);
    }
}
