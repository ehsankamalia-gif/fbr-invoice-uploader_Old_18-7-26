<script setup>
import { ref, onMounted } from 'vue';
import { getSpareLedgerTransactions } from '../../api/admin';
import { fmt, fmtDateTime } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const totalCredits = ref(0);
const totalDebits = ref(0);
const closingBalance = ref(0);
const transactions = ref([]);
const uniqueMonths = ref([]);
const selectedMonth = ref('');
const selectedTransType = ref('');

async function load() {
  loading.value = true;
  const params = {};
  if (selectedMonth.value) params.month = selectedMonth.value;
  if (selectedTransType.value) params.trans_type = selectedTransType.value;
  const data = await getSpareLedgerTransactions(params);
  totalCredits.value = data.total_credits;
  totalDebits.value = data.total_debits;
  closingBalance.value = data.closing_balance;
  transactions.value = data.transactions;
  uniqueMonths.value = data.unique_months;
  loading.value = false;
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-cogs mr-3"></i>Spare Parts Ledger - Transactions</h1>
      <p class="text-gray-600">View and filter spare parts ledger transactions</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
      <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-green-500">
        <h3 class="text-sm text-gray-600 font-semibold mb-2">Total Credits (In)</h3>
        <p class="text-3xl font-bold text-green-600">{{ fmt(totalCredits) }}</p>
      </div>
      <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-red-500">
        <h3 class="text-sm text-gray-600 font-semibold mb-2">Spare Part Order</h3>
        <p class="text-3xl font-bold text-red-600">{{ fmt(totalDebits) }}</p>
      </div>
      <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-blue-500">
        <h3 class="text-sm text-gray-600 font-semibold mb-2">Current Balance</h3>
        <p class="text-3xl font-bold text-blue-600">{{ fmt(closingBalance) }}</p>
        <p class="text-xs text-gray-500 mt-1">Take from Ehsan Traders</p>
      </div>
    </div>

    <div class="bg-white rounded-xl p-6 card-shadow mb-6">
      <div class="flex flex-wrap gap-4 items-end">
        <div class="flex-1 min-w-[200px]">
          <label class="block text-sm font-medium text-gray-700 mb-2"><i class="fas fa-calendar-alt mr-2 text-gray-500"></i>Select Month</label>
          <select v-model="selectedMonth" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
            <option value="">All Months</option>
            <option v-for="m in uniqueMonths" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div class="flex-1 min-w-[200px]">
          <label class="block text-sm font-medium text-gray-700 mb-2"><i class="fas fa-exchange-alt mr-2 text-gray-500"></i>Transaction Type</label>
          <select v-model="selectedTransType" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
            <option value="">All Types</option>
            <option value="CREDIT">Credit (Deposit)</option>
            <option value="DEBIT">SP Order (Debit)</option>
          </select>
        </div>
        <div>
          <button @click="load" class="w-full px-6 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition">
            <i class="fas fa-filter mr-2"></i>Apply Filters
          </button>
        </div>
      </div>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Date/Time</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Source</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Reference</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Description</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Credit (In)</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">SP Order</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Balance</th>
              <th class="text-left py-3 px-2 text-sm font-semibold text-gray-600">Month</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(tx, i) in transactions" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-3 px-2 text-sm text-gray-600">{{ fmtDateTime(tx.timestamp) }}</td>
              <td class="py-3 px-2 text-sm text-gray-800">{{ tx.cash_type_display }}</td>
              <td class="py-3 px-2 text-sm text-gray-800">{{ tx.reference_number || '-' }}</td>
              <td class="py-3 px-2 text-sm text-gray-800">{{ tx.description || '-' }}</td>
              <td class="py-3 px-2 text-sm font-semibold text-green-600">{{ tx.trans_type === 'CREDIT' ? fmt(tx.amount) : '-' }}</td>
              <td class="py-3 px-2 text-sm font-semibold text-red-600">{{ tx.trans_type === 'DEBIT' ? fmt(tx.amount) : '-' }}</td>
              <td class="py-3 px-2 text-sm font-bold text-blue-600">{{ fmt(tx.balance) }}</td>
              <td class="py-3 px-2 text-sm text-gray-800">{{ tx.month_key }}</td>
            </tr>
            <tr v-if="!transactions.length">
              <td colspan="8" class="py-8 text-center text-gray-500">
                <i class="fas fa-inbox fa-2x mb-2"></i>
                <p>No transactions found{{ selectedMonth || selectedTransType ? ' for the selected filters' : '' }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
