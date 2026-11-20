const express = require('express')
const app = express()

app.get('/ola', (req, res) => {
  res.send('<h1>Ola, ' + req.query.nome + '</h1>')
})

module.exports = app
