import { describe, expect, it } from 'vitest'

import {
  explorerBlockUrl,
  explorerContractUrl,
  explorerTxUrl,
  explorerTxUrlFor,
} from '@/lib/explorer'

const HASH = '0x' + '22'.repeat(32)

describe('explorerTxUrl', () => {
  it('accepts a transaction page on the Amoy explorer', () => {
    const url = `https://amoy.polygonscan.com/tx/${HASH}`
    expect(explorerTxUrl(url)).toBe(url)
    expect(
      explorerTxUrl(`https://amoy.polygonscan.com/tx/${'22'.repeat(32)}`),
    ).not.toBeNull()
  })

  it('rejects other schemes', () => {
    for (const value of [
      `http://amoy.polygonscan.com/tx/${HASH}`,
      `javascript:alert(1)//amoy.polygonscan.com/tx/${HASH}`,
      'data:text/html,<script>alert(1)</script>',
      `ftp://amoy.polygonscan.com/tx/${HASH}`,
      `//amoy.polygonscan.com/tx/${HASH}`,
    ]) {
      expect(explorerTxUrl(value), value).toBeNull()
    }
  })

  it('rejects other hosts, lookalikes, ports and embedded credentials', () => {
    for (const value of [
      `https://polygonscan.com/tx/${HASH}`,
      `https://evil.example/tx/${HASH}`,
      `https://amoy.polygonscan.com.evil.example/tx/${HASH}`,
      `https://evil.example/amoy.polygonscan.com/tx/${HASH}`,
      `https://amoy.polygonscan.com@evil.example/tx/${HASH}`,
      `https://amoy.polygonscan.com:8443/tx/${HASH}`,
      `https://user:pw@amoy.polygonscan.com/tx/${HASH}`,
      `https://amoy-polygonscan.com/tx/${HASH}`,
    ]) {
      expect(explorerTxUrl(value), value).toBeNull()
    }
  })

  it('rejects other pages on the explorer and odd paths', () => {
    for (const value of [
      'https://amoy.polygonscan.com/',
      `https://amoy.polygonscan.com/address/${HASH}`,
      'https://amoy.polygonscan.com/tx/',
      'https://amoy.polygonscan.com/tx/not-a-hash',
      `https://amoy.polygonscan.com/tx/${HASH}/../../x`,
      `https://amoy.polygonscan.com//tx/${HASH}`,
    ]) {
      expect(explorerTxUrl(value), value).toBeNull()
    }
  })

  it('rejects empty and unparseable values', () => {
    expect(explorerTxUrl(null)).toBeNull()
    expect(explorerTxUrl(undefined)).toBeNull()
    expect(explorerTxUrl('')).toBeNull()
    expect(explorerTxUrl('not a url')).toBeNull()
  })
})

describe('explorerTxUrlFor', () => {
  it('builds the link from a stored hash', () => {
    expect(explorerTxUrlFor(HASH)).toBe(
      `https://amoy.polygonscan.com/tx/${HASH}`,
    )
  })

  it('refuses a stored value that is not a hash', () => {
    expect(explorerTxUrlFor('../../evil')).toBeNull()
    expect(explorerTxUrlFor('0x1/../../x')).toBeNull()
  })
})

describe('explorerContractUrl', () => {
  const ADDRESS = '0x' + 'ab'.repeat(20)

  it('accepts the contract page, with or without the read tab', () => {
    const url = `https://amoy.polygonscan.com/address/${ADDRESS}`
    expect(explorerContractUrl(url)).toBe(url)
    expect(explorerContractUrl(`${url}#readContract`)).toBe(
      `${url}#readContract`,
    )
  })

  it('rejects other hosts, schemes, paths, queries and fragments', () => {
    for (const value of [
      `https://evil.example/address/${ADDRESS}`,
      `http://amoy.polygonscan.com/address/${ADDRESS}`,
      `https://amoy.polygonscan.com/tx/${HASH}`,
      `https://amoy.polygonscan.com/address/${ADDRESS}?next=//evil.example`,
      `https://amoy.polygonscan.com/address/${ADDRESS}#other`,
      `https://amoy.polygonscan.com@evil.example/address/${ADDRESS}`,
      'https://amoy.polygonscan.com/address/0x1234',
      '',
      null,
    ]) {
      expect(explorerContractUrl(value), String(value)).toBeNull()
    }
  })
})

describe('explorerBlockUrl', () => {
  it('builds a block link from a positive whole number only', () => {
    expect(explorerBlockUrl(51378532)).toBe(
      'https://amoy.polygonscan.com/block/51378532',
    )
    for (const value of [0, -1, 1.5, Number.NaN, Number.MAX_VALUE]) {
      expect(explorerBlockUrl(value), String(value)).toBeNull()
    }
  })
})
