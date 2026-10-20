// Read the public SSR data as literals. Never evaluate page JavaScript.
const fs = require('fs')
const acorn = require('../../frontend/node_modules/acorn')
const [input, output] = process.argv.slice(2)
if (!input || !output) throw Error('Usage: node tools/collect/weshine-state.cjs input.html output.json')
const html = fs.readFileSync(input, 'utf8')
if (Buffer.byteLength(html) > 2 * 1024 * 1024) throw Error('Page too large')
const match = html.match(/<script[^>]*>(window\.__NUXT__=[\s\S]*?)<\/script>/)
if (!match) throw Error('No SSR state')
const ast = acorn.parse(match[1], {ecmaVersion: 2020})
if (ast.body.length !== 1) throw Error('Unexpected state program')
const assignment = ast.body[0].expression
if (assignment.type !== 'AssignmentExpression' || assignment.left.object?.name !== 'window' || assignment.left.property?.name !== '__NUXT__') throw Error('Unexpected state assignment')
let nodes = 0
function literal(node, env = {}, depth = 0) {
  if (++nodes > 100000 || depth > 60) throw Error('State bounds exceeded')
  if (node.type === 'Literal' && !node.regex) return node.value
  if (node.type === 'Identifier' && Object.hasOwn(env, node.name)) return env[node.name]
  if (node.type === 'ArrayExpression') return node.elements.map(n => literal(n, env, depth + 1))
  if (node.type === 'ObjectExpression') {
    const result = Object.create(null)
    for (const prop of node.properties) {
      if (prop.type !== 'Property' || prop.computed || prop.method || prop.kind !== 'init') throw Error('Nonliteral property')
      const key = prop.key.name ?? prop.key.value
      if (['__proto__', 'constructor', 'prototype'].includes(key)) throw Error('Unsafe key')
      result[key] = literal(prop.value, env, depth + 1)
    }
    return result
  }
  if (node.type === 'UnaryExpression' && ['-', '!', '+'].includes(node.operator)) {
    const value = literal(node.argument, env, depth + 1)
    return node.operator === '-' ? -value : node.operator === '+' ? +value : !value
  }
  throw Error('Nonliteral state node: ' + node.type)
}
let data
const value = assignment.right
if (value.type === 'CallExpression') {
  const fn = value.callee
  if (fn.type !== 'FunctionExpression' || fn.async || fn.generator || fn.body.body.length !== 1 || fn.body.body[0].type !== 'ReturnStatement') throw Error('Nonliteral state wrapper')
  const env = Object.create(null)
  if (fn.params.length !== value.arguments.length) throw Error('State argument mismatch')
  fn.params.forEach((param, index) => {
    if (param.type !== 'Identifier') throw Error('Nonliteral state parameter')
    env[param.name] = literal(value.arguments[index])
  })
  data = literal(fn.body.body[0].argument, env)
} else data = literal(value)
fs.writeFileSync(output, JSON.stringify(data, null, 2) + '\n')
console.log(JSON.stringify({data: data.data?.map(item => Object.keys(item)), output}))
