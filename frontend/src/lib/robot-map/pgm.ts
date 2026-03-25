export type ParsedPgm = {
  width: number
  height: number
  pixels: Uint8Array
}

function isWhitespace(value: number) {
  return value === 0x20 || value === 0x09 || value === 0x0a || value === 0x0d
}

function readToken(bytes: Uint8Array, cursor: { index: number }) {
  while (cursor.index < bytes.length) {
    const value = bytes[cursor.index]
    if (value === 0x23) {
      while (cursor.index < bytes.length && bytes[cursor.index] !== 0x0a) {
        cursor.index += 1
      }
      continue
    }
    if (isWhitespace(value)) {
      cursor.index += 1
      continue
    }
    break
  }

  const start = cursor.index
  while (cursor.index < bytes.length) {
    const value = bytes[cursor.index]
    if (value === 0x23 || isWhitespace(value)) {
      break
    }
    cursor.index += 1
  }

  if (start === cursor.index) {
    return ''
  }

  return new TextDecoder('ascii').decode(bytes.slice(start, cursor.index))
}

export function parsePgm(buffer: ArrayBuffer): ParsedPgm {
  const bytes = new Uint8Array(buffer)
  const cursor = { index: 0 }
  const magic = readToken(bytes, cursor)
  const width = Number(readToken(bytes, cursor))
  const height = Number(readToken(bytes, cursor))
  const maxValue = Number(readToken(bytes, cursor))

  if ((magic !== 'P5' && magic !== 'P2') || !Number.isFinite(width) || !Number.isFinite(height)) {
    throw new Error('지원하지 않는 PGM 형식입니다.')
  }

  if (!Number.isFinite(maxValue) || maxValue <= 0 || maxValue > 255) {
    throw new Error('8비트 PGM만 지원합니다.')
  }

  while (cursor.index < bytes.length && isWhitespace(bytes[cursor.index])) {
    cursor.index += 1
  }

  const pixelCount = width * height

  if (magic === 'P5') {
    const pixelBytes = bytes.slice(cursor.index, cursor.index + pixelCount)
    if (pixelBytes.length !== pixelCount) {
      throw new Error('PGM 픽셀 길이가 올바르지 않습니다.')
    }
    return { width, height, pixels: pixelBytes }
  }

  const asciiTokens: number[] = []
  while (asciiTokens.length < pixelCount) {
    const token = readToken(bytes, cursor)
    if (!token) {
      break
    }
    asciiTokens.push(Number(token))
  }
  if (asciiTokens.length !== pixelCount) {
    throw new Error('ASCII PGM 픽셀 길이가 올바르지 않습니다.')
  }
  return {
    width,
    height,
    pixels: Uint8Array.from(asciiTokens),
  }
}
