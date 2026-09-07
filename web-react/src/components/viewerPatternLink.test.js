import { parseViewerPatternLink, linkedPatternDirection, includeSelectedWindowOption } from './viewerPatternLink'

const resources = {'2':'S&P 500 STOCKS', '5':'US INDICES'}
const query = (payload, suffix='') => '?o=' + encodeURIComponent(window.btoa(payload).replace(/=+$/,'')) + suffix

test('MCP evidence link carries the exact window and direction', () => {
  const link = parseViewerPatternLink(query('2|aapl|2026-09-01|30|10', '&direction=long&view=evidence'), resources)
  expect(link).toEqual({market:'2',resource:'S&P 500 STOCKS',symbol:'AAPL',date:'2026-09-01',days:'30',years:'10',direction:'long'})
  expect(linkedPatternDirection(link, link)).toBe('long')
  expect(linkedPatternDirection(link, {...link, symbol:'MSFT'})).toBeNull()
  expect(linkedPatternDirection(link, {...link, days:31})).toBeNull()
})

test.each([
  '?o=not-base64!', query('2|AAPL'), query('99|AAPL|2026-09-01|30|10'),
  query('2|AAPL|2026-02-30|30|10'), query('2|AAPL|2026-09-01|0|10'),
  query('2|AAPL|2026-09-01|368|10'), query('2|AAPL|2026-09-01|30|pe9'),
  query('2|AAPL|2026-09-01|30|NaN'), query('2|AAPL|2026-09-01|30|10', '&direction=sideways'),
])('malformed link fails atomically without throwing: %s', search => {
  expect(parseViewerPatternLink(search, resources)).toBeNull()
})

test('existing directionless links and PE reports still parse', () => {
  expect(parseViewerPatternLink(query('5|SPX|2026-01-01|366|PE2-24'), resources)).toMatchObject({years:'pe2-24',direction:null})
  expect(parseViewerPatternLink(query('2|AAPL|2026-09-01|30|10'), resources)).toMatchObject({years:'10',direction:null})
  expect(parseViewerPatternLink(query('5|DJI|2026-09-01|30|120'), resources)).toMatchObject({years:'120'})
})

test('custom one-day and three-year analysis does not display the first dropdown option', () => {
  const options = [{id:5,value:'5',label:'5'}, {id:10,value:'10',label:'10'}]
  expect(includeSelectedWindowOption(options, '3', 999)[0].value).toBe('3')
  expect(includeSelectedWindowOption(options, '1', 367)[0].value).toBe('1')
  expect(includeSelectedWindowOption(options, '5', 999)).toBe(options)
  expect(includeSelectedWindowOption(options, 'bad', 999)).toBe(options)
})
