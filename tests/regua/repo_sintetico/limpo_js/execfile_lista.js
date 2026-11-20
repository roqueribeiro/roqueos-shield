const { execFile } = require('child_process')

function versaoDoGit(callback) {
  execFile('git', ['--version'], (err, out) => callback(err, out))
}

module.exports = { versaoDoGit }
