import express from 'express'
import { Pool } from 'pg'

const app = express()
const pool = new Pool()

app.get('/pedido', async (req, res) => {
  const r = await pool.query(`SELECT * FROM pedidos WHERE cliente = '${req.query.cliente}'`)
  res.json(r.rows)
})

export default app
