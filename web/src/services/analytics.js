// O standalone não manda telemetria para lugar nenhum. A tela portada chama
// `trackFeature`; aqui ela não faz nada, de propósito (ambiente regulado).
export function trackFeature() {}
export default { trackFeature }
