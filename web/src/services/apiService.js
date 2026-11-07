// O pedaço do `apiService` do RoqueOS que a tela do RoqueShield usa: o uso de
// máquina. No RoqueOS ele lê o host do servidor; aqui, o container do shield.
import { get } from './http'

export default {
  async getSystemStats() {
    const u = await get('/system/usage')
    if (!u?.disponivel) throw new Error('uso indisponível')
    return {
      host: { cpuPercent: u.cpuPercent, memoryUsed: u.memUsage, memoryTotal: u.memLimit },
    }
  },
}
