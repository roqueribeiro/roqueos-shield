import java.security.MessageDigest;

public class HashForte {
    public byte[] resumo(byte[] dados) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(dados);
    }
}
