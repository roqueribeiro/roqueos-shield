const mysql = require('mysql')
const connection = mysql.createConnection({ host: 'db' })

function buscar(id, callback) {
  connection.query('SELECT * FROM users WHERE id = ?', [id], callback)
}

module.exports = { buscar }
