import {
  Badge,
  Button,
  GlyphSpinner,
  host,
  Input,
  PALETTE_AREA,
  Textarea,
  useValue
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'hermes-model-router'
const SAFE_VALUE = /^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$/
const STATUS_MODEL = /^Model:\s*(.+?)\s*\(([^()]+)\)\s*$/m
const STATUS_RUNNING = /^Agent Running:\s*(Yes|No)\s*$/im

function encodeTask(text) {
  const bytes = new TextEncoder().encode(text)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '')
}

function parseStatus(result, sessionId) {
  const output = String(result?.output || '')
  const model = STATUS_MODEL.exec(output)
  const running = STATUS_RUNNING.exec(output)
  if (!model || !running) throw new Error('Hermes returned an incomplete session status')
  return {
    sessionId,
    model: model[1].trim(),
    provider: model[2].trim(),
    running: running[1].toLowerCase() === 'yes'
  }
}

async function readSession(sessionId) {
  return parseStatus(await host.request('session.status', { session_id: sessionId }), sessionId)
}

function validateProposal(proposal) {
  if (!proposal || proposal.error) throw new Error(proposal?.error || 'Router returned no proposal')
  if (!SAFE_VALUE.test(proposal.provider || '') || !SAFE_VALUE.test(proposal.model || '')) {
    throw new Error('Router returned an unsafe provider or model value')
  }
  if (proposal.scope !== 'session' || proposal.approval_required !== true || proposal.switched !== false) {
    throw new Error('Router proposal violated the approval contract')
  }
  const expected = `/model ${proposal.model} --provider ${proposal.provider} --session`
  if (proposal.session_command !== expected || proposal.session_command.includes('--global')) {
    throw new Error('Router returned a non-session-only command')
  }
  return proposal
}

function sameSnapshot(left, right) {
  return Boolean(
    left &&
      right &&
      left.sessionId === right.sessionId &&
      left.provider === right.provider &&
      left.model === right.model &&
      left.running === right.running
  )
}

function RouterPane() {
  const focusedSessionId = useValue(host.state.focusedSessionId)
  const activeModel = useValue(host.state.model)
  const [task, setTask] = useState('')
  const [budget, setBudget] = useState('')
  const [proposal, setProposal] = useState(null)
  const [expected, setExpected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')

  const propose = async () => {
    const sessionId = String(host.state.focusedSessionId.get() || '')
    if (!sessionId) {
      setError('Open a Hermes session before routing a task.')
      return
    }
    if (!task.trim()) {
      setError('Enter a task to route.')
      return
    }
    setBusy(true)
    setError('')
    setResult('')
    setProposal(null)
    try {
      const before = await readSession(sessionId)
      if (before.running) throw new Error('The active session is busy; wait for the turn to finish.')
      const budgetArg = budget.trim() ? ` --budget ${Number(budget)}` : ''
      if (budget.trim() && (!Number.isFinite(Number(budget)) || Number(budget) < 0)) {
        throw new Error('Budget must be a non-negative number.')
      }
      const response = await host.request('slash.exec', {
        session_id: sessionId,
        command: `/route --json${budgetArg} --task-b64 ${encodeTask(task.trim())}`
      })
      const routed = validateProposal(JSON.parse(String(response?.output || '')))
      setExpected(before)
      setProposal(routed)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  const approveAndSwitch = async () => {
    if (!proposal || !expected) return
    setBusy(true)
    setError('')
    setResult('')
    try {
      const sessionId = String(host.state.focusedSessionId.get() || '')
      if (!sessionId || sessionId !== expected.sessionId) {
        throw new Error('Approval is stale: the active session changed.')
      }
      const current = await readSession(sessionId)
      if (current.running) throw new Error('The active session is busy; no switch was attempted.')
      if (!sameSnapshot(current, expected)) {
        throw new Error('Approval is stale: the active provider or model changed.')
      }

      const command = `/model ${proposal.model} --provider ${proposal.provider} --session`
      const switchResult = await host.request('slash.exec', {
        session_id: sessionId,
        command
      })
      if (switchResult?.confirm_required) {
        throw new Error('Hermes requires an additional model confirmation; no approval was assumed.')
      }
      if (/session busy/i.test(String(switchResult?.output || ''))) {
        throw new Error(String(switchResult.output))
      }

      const after = await readSession(sessionId)
      if (after.running || after.provider !== proposal.provider || after.model !== proposal.model) {
        throw new Error('Post-switch verification failed.')
      }
      setResult(`Switched this session to ${after.provider}/${after.model}. Your task was not sent automatically.`)
      setProposal(null)
      setExpected(null)
      host.notify({ kind: 'success', message: `Session switched to ${after.provider}/${after.model}` })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return jsxs('div', {
    className: 'flex h-full flex-col gap-3 p-3 text-sm',
    children: [
      jsxs('div', {
        className: 'grid gap-1',
        children: [
          jsx('div', { className: 'font-medium', children: 'Hermes Model Router' }),
          jsx('div', {
            className: 'text-xs text-(--ui-text-tertiary)',
            children: `Active model: ${activeModel || 'unknown'}`
          })
        ]
      }),
      jsx(Textarea, {
        'aria-label': 'Task to route',
        className: 'min-h-28 resize-y',
        placeholder: 'Describe the task you want Hermes to perform…',
        value: task,
        onChange: event => {
          setTask(event.target.value)
          setProposal(null)
          setExpected(null)
          setResult('')
        }
      }),
      jsx(Input, {
        'aria-label': 'Optional cost budget',
        inputMode: 'decimal',
        min: '0',
        placeholder: 'Optional $/1M output-token budget',
        type: 'number',
        value: budget,
        onChange: event => {
          setBudget(event.target.value)
          setProposal(null)
          setExpected(null)
        }
      }),
      jsx(Button, {
        disabled: busy || !task.trim() || !focusedSessionId,
        onClick: propose,
        children: busy ? jsxs('span', { className: 'flex items-center gap-2', children: [jsx(GlyphSpinner, { spinner: 'breathe' }), 'Checking…'] }) : 'Propose route'
      }),
      proposal
        ? jsxs('div', {
            className: 'grid gap-2 rounded-md border border-(--ui-stroke-secondary) p-2.5',
            children: [
              jsxs('div', {
                className: 'flex flex-wrap items-center gap-1.5',
                children: [
                  jsx(Badge, { children: proposal.task }),
                  jsx(Badge, { variant: 'secondary', children: `confidence ${Number(proposal.confidence).toFixed(2)}` })
                ]
              }),
              jsx('div', { className: 'font-medium', children: `${proposal.provider}/${proposal.model}` }),
              jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: proposal.reason }),
              jsx('div', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: `$${Number(proposal.cost_per_million_output).toFixed(2)} per 1M output tokens`
              }),
              jsx('div', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: 'Approval applies only to this exact session and route. Switching resets prompt-cache continuity.'
              }),
              jsx(Button, {
                disabled: busy,
                onClick: approveAndSwitch,
                children: `Approve and switch this session to ${proposal.model}`
              })
            ]
          })
        : null,
      error ? jsx('div', { className: 'text-xs text-(--ui-danger)', role: 'alert', children: error }) : null,
      result ? jsx('div', { className: 'text-xs text-(--ui-text-secondary)', role: 'status', children: result }) : null,
      jsx('div', {
        className: 'mt-auto text-[0.6875rem] text-(--ui-text-quaternary)',
        children: 'No global config writes. No automatic task submission. Hermes fallback remains unchanged.'
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Hermes Model Router',
  description: 'Propose cost-aware routes and explicitly approve verified session-only model switches.',
  defaultEnabled: false,
  register(ctx) {
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'Model Router',
      data: { placement: 'right', width: '320px' },
      render: () => jsx(RouterPane, {})
    })
    ctx.register({
      id: 'open-router',
      area: PALETTE_AREA,
      data: {
        id: `${ID}.open-router`,
        label: 'Open Model Router',
        keywords: ['model', 'router', 'cost', 'provider'],
        run: () => host.notify({ kind: 'info', message: 'Open the Model Router pane from the layout.' })
      }
    })
  }
}
