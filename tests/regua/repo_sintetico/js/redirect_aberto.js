const express = require('express')
const app = express()

app.get('/login/callback', (req, res) => {
  res.redirect(req.query.next)
})

module.exports = app
