import java.io.IOException;
import java.io.ObjectInputStream;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public class DesserializaEntrada extends HttpServlet {
    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        ObjectInputStream in = new ObjectInputStream(request.getInputStream());
        try {
            Object pedido = in.readObject();
            response.getWriter().print(pedido.toString());
        } catch (ClassNotFoundException e) {
            throw new IOException(e);
        }
    }
}
