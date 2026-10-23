import assert from 'node:assert/strict'
import test from 'node:test'
import { formatMetricValue, metricCurrentForUnit, summarizeMetricsByUnit } from '../src/lib/metric-display.ts'

test('currency labels follow the supplied unit without conversion', () => {
  assert.equal(formatMetricValue(1250, 'HKD'), 'HKD 1,250')
  assert.equal(formatMetricValue(1250, 'USD'), 'USD 1,250')
})

test('credit, counts and unknown units are preserved', () => {
  assert.equal(formatMetricValue(1250, 'Credit'), '1,250 Credit')
  assert.equal(formatMetricValue(12, 'cases'), '12 cases')
  assert.equal(formatMetricValue(2, '次'), '2 次')
  assert.equal(formatMetricValue(10, 'points'), '10 points')
})

test('missing units are not silently labelled as money', () => {
  assert.equal(formatMetricValue(500), '500')
  assert.equal(formatMetricValue(0), '0')
})

test('percentages keep the API ratio convention', () => {
  assert.equal(formatMetricValue(0.42, '%'), '42.0%')
  assert.equal(formatMetricValue(0, '%'), '0.0%')
})

test('missing and invalid values remain unavailable rather than zero', () => {
  for (const value of [null, undefined, NaN, Infinity, -Infinity]) {
    assert.equal(formatMetricValue(value, 'HKD'), '—')
  }
})

test('compact formatting retains the unit and does not change the currency', () => {
  assert.equal(formatMetricValue(3200000, 'Credit', true), '3.2M Credit')
  assert.equal(formatMetricValue(12000, 'HKD', true), 'HKD 12K')
  assert.equal(formatMetricValue(12000, 'USD', true), 'USD 12K')
})

test('team totals never combine HKD, USD and Credit', () => {
  assert.deepEqual(summarizeMetricsByUnit([
    { current: 10, target: 100, unit: 'HKD' },
    { current: 20, target: 200, unit: 'USD' },
    { current: 30, target: 300, unit: 'Credit' },
    { current: 5, target: 50, unit: 'HKD' },
    { current: null, target: 100, unit: 'USD' },
    { current: NaN, target: 100, unit: 'Credit' },
    { current: 0, target: 100, unit: 'cases' },
  ]), [
    { current: 15, target: 150, unit: 'HKD' },
    { current: 20, target: 200, unit: 'USD' },
    { current: 30, target: 300, unit: 'Credit' },
    { current: 0, target: 100, unit: 'cases' },
  ])
})

test('a target cannot compare values from different units or missing metrics', () => {
  assert.equal(metricCurrentForUnit({ current: 200, unit: 'HKD' }, 'USD'), null)
  assert.equal(metricCurrentForUnit({ current: 200, unit: 'HKD' }, 'Credit'), null)
  assert.equal(metricCurrentForUnit(undefined, 'HKD'), null)
  assert.equal(metricCurrentForUnit({ current: NaN, unit: 'HKD' }, 'HKD'), null)
  assert.equal(metricCurrentForUnit({ current: 0, unit: 'HKD' }, 'HKD'), 0)
  assert.equal(metricCurrentForUnit({ current: 200, unit: 'Credit' }, 'Credit'), 200)
})