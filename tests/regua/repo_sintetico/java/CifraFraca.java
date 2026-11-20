import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;

public class CifraFraca {
    public byte[] cifrar(byte[] chave, byte[] dados) throws Exception {
        Cipher c = Cipher.getInstance("DES/ECB/PKCS5Padding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(chave, "DES"));
        return c.doFinal(dados);
    }
}
