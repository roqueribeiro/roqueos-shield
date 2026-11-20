const express = require('express')
const app = express()
app.use(express.json())

app.post('/calc', (req, res) => {
  const resultado = eval(req.body.expressao)
  res.json({ resultado })
})

module.exports = app
