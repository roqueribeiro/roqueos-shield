const jwt = require('jsonwebtoken')

function emitir(usuario) {
  return jwt.sign({ sub: usuario.id }, 'segredo-de-producao-123', { expiresIn: '1h' })
}

module.exports = { emitir }
