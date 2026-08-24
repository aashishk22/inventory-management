<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ formatMoney(budget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.allocated') }}</div>
          <div class="stat-value">{{ formatMoney(totalCost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatMoney(remaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.setBudget') }}</h3>
        </div>
        <div class="slider-body">
          <div class="slider-value">{{ formatMoney(budget) }}</div>
          <input
            v-model.number="budget"
            type="range"
            class="budget-slider"
            :min="BUDGET_MIN"
            :max="BUDGET_MAX"
            :step="BUDGET_STEP"
            :aria-label="t('restocking.setBudget')"
          >
          <div class="slider-scale">
            <span>{{ formatMoney(BUDGET_MIN) }}</span>
            <span>{{ formatMoney(BUDGET_MAX) }}</span>
          </div>
          <div class="utilisation">
            <div class="utilisation-track">
              <div class="utilisation-fill" :style="{ width: utilisationPercent + '%' }"></div>
            </div>
            <span class="utilisation-label">
              {{ t('restocking.budgetUsed', { percent: utilisationPercent }) }}
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            {{ t('restocking.recommendations') }} ({{ recommendations.length }})
          </h3>
          <button
            class="place-order-btn"
            :disabled="!canSubmit"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="submitError" class="error submit-error">{{ submitError }}</div>
        <div v-if="successMessage" class="success-banner">{{ successMessage }}</div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>

        <div v-else class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th class="col-name">{{ t('restocking.table.itemName') }}</th>
                <th class="col-trend">{{ t('restocking.table.trend') }}</th>
                <th class="col-num">{{ t('restocking.table.shortfall') }}</th>
                <th class="col-num">{{ t('restocking.table.quantity') }}</th>
                <th class="col-num">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-num">{{ t('restocking.table.leadTime') }}</th>
                <th class="col-num">{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in recommendations" :key="rec.item_sku">
                <td class="col-sku"><strong>{{ rec.item_sku }}</strong></td>
                <td class="col-name">{{ translateProductName(rec.item_name) }}</td>
                <td class="col-trend">
                  <span :class="['badge', rec.trend]">{{ t(`trends.${rec.trend}`) }}</span>
                </td>
                <td class="col-num">{{ rec.shortfall.toLocaleString() }}</td>
                <td class="col-num">
                  <strong>{{ rec.quantity.toLocaleString() }}</strong>
                  <span v-if="rec.partial" class="partial-flag">
                    {{ t('restocking.partial') }}
                  </span>
                </td>
                <td class="col-num">{{ formatMoneyExact(rec.unit_cost) }}</td>
                <td class="col-num">{{ t('restocking.days', { count: rec.lead_time_days }) }}</td>
                <td class="col-num"><strong>{{ formatMoney(rec.line_total) }}</strong></td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="7" class="foot-label">{{ t('restocking.orderTotal') }}</td>
                <td class="col-num"><strong>{{ formatMoney(totalCost) }}</strong></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.skipped') }} ({{ skipped.length }})</h3>
        </div>
        <div v-if="skipped.length === 0" class="empty-state">
          {{ t('restocking.nothingSkipped') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.reason') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in skipped" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td><span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span></td>
                <td class="reason">{{ item.reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

// Slider bounds. The step is coarse enough that dragging feels responsive
// but fine enough to land just under an individual item's line total.
const BUDGET_MIN = 0
const BUDGET_MAX = 250000
const BUDGET_STEP = 1000
const DEFAULT_BUDGET = 50000

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(DEFAULT_BUDGET)
    const submitting = ref(false)
    const submitError = ref(null)
    const successMessage = ref(null)

    const formatMoney = (amount) => formatCurrency(amount, currentCurrency.value)
    const formatMoneyExact = (amount) =>
      formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

    // Candidates are forecast rows whose forecasted demand exceeds current
    // demand. A non-positive shortfall means the item is already covered, so
    // it is never worth spending budget on.
    const candidates = computed(() => {
      return forecasts.value
        .map(f => ({
          ...f,
          shortfall: f.forecasted_demand - f.current_demand
        }))
        .filter(f => f.shortfall > 0)
        // Largest shortfall first: the most under-supplied item gets funded
        // before anything else.
        .sort((a, b) => b.shortfall - a.shortfall)
    })

    // Greedy fill: walk the ranked candidates and buy each item's full
    // shortfall while the budget covers it. When the remaining budget covers
    // only part of a line, buy the affordable whole units and keep going —
    // a later, cheaper item may still fit entirely.
    const allocation = computed(() => {
      let remainingBudget = budget.value
      const chosen = []
      const rejected = []

      for (const candidate of candidates.value) {
        const fullCost = candidate.shortfall * candidate.unit_cost

        if (fullCost <= remainingBudget) {
          chosen.push({
            ...candidate,
            quantity: candidate.shortfall,
            line_total: round2(fullCost),
            partial: false
          })
          remainingBudget -= fullCost
          continue
        }

        // Only whole units can be ordered, so floor rather than round.
        const affordableUnits = Math.floor(remainingBudget / candidate.unit_cost)

        if (affordableUnits > 0) {
          const partialCost = affordableUnits * candidate.unit_cost
          chosen.push({
            ...candidate,
            quantity: affordableUnits,
            line_total: round2(partialCost),
            partial: true
          })
          remainingBudget -= partialCost
        } else {
          rejected.push({
            ...candidate,
            reason: t('restocking.reasonUnaffordable', {
              // Exact cents here: the whole point of this row is that the
              // remaining budget fell short of this price, and rounding
              // $18.90 to $19 makes the comparison look wrong.
              cost: formatMoneyExact(candidate.unit_cost)
            })
          })
        }
      }

      return { chosen, rejected }
    })

    const recommendations = computed(() => allocation.value.chosen)

    // Two ways an item misses out: it was ranked but unaffordable, or its
    // forecast never showed a shortfall in the first place.
    const skipped = computed(() => {
      const covered = forecasts.value
        .filter(f => f.forecasted_demand - f.current_demand <= 0)
        .map(f => ({ ...f, reason: t('restocking.reasonCovered') }))

      return [...allocation.value.rejected, ...covered]
    })

    const totalCost = computed(() =>
      round2(recommendations.value.reduce((sum, r) => sum + r.line_total, 0))
    )

    const remaining = computed(() => round2(budget.value - totalCost.value))

    const utilisationPercent = computed(() => {
      if (budget.value <= 0) return 0
      return Math.round((totalCost.value / budget.value) * 100)
    })

    const canSubmit = computed(() =>
      recommendations.value.length > 0 && !submitting.value
    )

    const loadForecasts = async () => {
      try {
        loading.value = true
        forecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      submitting.value = true
      submitError.value = null
      successMessage.value = null

      try {
        const payload = {
          budget: budget.value,
          items: recommendations.value.map(r => ({
            item_sku: r.item_sku,
            item_name: r.item_name,
            quantity: r.quantity,
            unit_cost: r.unit_cost,
            lead_time_days: r.lead_time_days,
            line_total: r.line_total
          }))
        }

        const order = await api.createRestockOrder(payload)
        successMessage.value = t('restocking.submitted', {
          orderNumber: order.order_number,
          days: order.lead_time_days
        })
      } catch (err) {
        submitError.value =
          err.response?.data?.detail || 'Failed to place order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      recommendations,
      skipped,
      totalCost,
      remaining,
      utilisationPercent,
      canSubmit,
      submitting,
      submitError,
      successMessage,
      placeOrder,
      formatMoney,
      formatMoneyExact,
      translateProductName,
      BUDGET_MIN,
      BUDGET_MAX,
      BUDGET_STEP
    }
  }
}

// Currency arithmetic accumulates binary float error across many line items,
// so every running total is snapped back to cents.
function round2(value) {
  return Math.round(value * 100) / 100
}
</script>

<style scoped>
.slider-body {
  padding: 1.5rem;
}

.slider-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
}

.budget-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.utilisation {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1.25rem;
}

.utilisation-track {
  flex: 1;
  height: 8px;
  background: #f1f5f9;
  border-radius: 4px;
  overflow: hidden;
}

.utilisation-fill {
  height: 100%;
  background: #10b981;
  border-radius: 4px;
  transition: width 0.2s ease;
}

.utilisation-label {
  font-size: 0.813rem;
  color: #64748b;
  white-space: nowrap;
}

.place-order-btn {
  background: #3b82f6;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #2563eb;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.success-banner {
  margin: 0 1.5rem 1rem;
  padding: 0.75rem 1rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 6px;
  color: #047857;
  font-size: 0.875rem;
}

.submit-error {
  margin: 0 1.5rem 1rem;
}

.empty-state {
  padding: 2rem 1.5rem;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.restock-table {
  table-layout: fixed;
  width: 100%;
}

.col-sku {
  width: 110px;
}

.col-name {
  width: 220px;
}

.col-trend {
  width: 120px;
}

.col-num {
  width: 110px;
  text-align: right;
}

.foot-label {
  text-align: right;
  color: #64748b;
  font-size: 0.875rem;
}

tfoot td {
  border-top: 2px solid #e2e8f0;
  background: #f8fafc;
}

.partial-flag {
  display: block;
  font-size: 0.688rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #d97706;
}

.reason {
  color: #64748b;
  font-size: 0.875rem;
}
</style>
