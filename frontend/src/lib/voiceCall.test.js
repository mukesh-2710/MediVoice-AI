import assert from 'node:assert/strict'
import test from 'node:test'
import { VoiceCall } from './voiceCall.js'

test('playAudio reports successful playback', async () => {
  const states = []
  const call = new VoiceCall({
    audioEl: { play: async () => {} },
    onPlaybackBlocked: (blocked) => states.push(blocked),
  })

  assert.equal(await call.playAudio(), true)
  assert.deepEqual(states, [false])
})

test('playAudio surfaces browser playback rejection', async () => {
  const states = []
  const call = new VoiceCall({
    audioEl: { play: async () => { throw new Error('autoplay blocked') } },
    onPlaybackBlocked: (blocked) => states.push(blocked),
  })

  assert.equal(await call.playAudio(), false)
  assert.deepEqual(states, [true])
})
