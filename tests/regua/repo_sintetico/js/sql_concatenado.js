const express = require('express')
const mysql = require('mysql')
const app = express()
const connection = mysql.createConnection({ host: 'db' })

app.get('/user/:id', (req, res) => {
  connection.query('SELECT * FROM users WHERE id = ' + req.params.id, (err, rows) => {
    res.json(rows)
  })
})

module.exports = app
