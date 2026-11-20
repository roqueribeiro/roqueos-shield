import express from 'express'
import * as fs from 'fs'
import * as path from 'path'

const app = express()

app.get('/arquivo', (req, res) => {
  const caminho = path.join('/srv/publico', req.query.nome as string)
  res.send(fs.readFileSync(caminho))
})

export default app
