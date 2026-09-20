<script setup>
import { ref, onMounted, computed } from 'vue';
import { getSpareLedgerMonthlySummary } from '../../api/admin';
import { fmt } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const reportData = ref([]);
const currentBalance = ref(0);

const totalBankCredit = computed(() => reportData.value.reduce((s, r) => s + r.bank_credit, 0));
const totalCashCredit = computed(() => reportData.value.reduce((s, r) => s + r.cash_credit, 0));
const totalSpOrder = computed(() => reportData.value.reduce((s, r) => s + r.sp_order, 0));

onMounted(async () => {
  const data = await getSpareLedgerMonthlySummary();
  reportData.value = data.report_data;
  currentBalance.value = data.current_balance;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-calendar mr-3"></i>Spare Parts Ledger - Monthly Summary</h1>
      <p class="text-gray-600">Monthly closing summary for spare parts ledger</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="bg-white rounded-xl p-6 card-shadow">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Date</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Previous Month Balance</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Bank Credit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Cash Credit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">SP Order</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Monthly Balance</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(m, i) in reportData" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-2 text-sm font-semibold text-gray-800">{{ m.date }}</td>
                <td class="py-3 px-2 text-sm text-gray-800">{{ fmt(m.previous_month_balance) }}</td>
                <td class="py-3 px-2 text-sm text-green-600 font-semibold">{{ fmt(m.bank_credit) }}</td>
                <td class="py-3 px-2 text-sm text-green-600 font-semibold">{{ fmt(m.cash_credit) }}</td>
                <td class="py-3 px-2 text-sm text-red-600 font-semibold">{{ fmt(m.sp_order) }}</td>
                <td class="py-3 px-2 text-sm font-bold text-blue-600">{{ fmt(m.monthly_balance) }}</td>
              </tr>
              <tr v-if="!reportData.length">
                <td colspan="6" class="py-8 text-center text-gray-500">
                  <i class="fas fa-calendar-times fa-2x mb-2"></i>
                  <p>No monthly summary data available</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="reportData.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-6">
        <div class="bg-white rounded-xl p-6 card-shadow card-hover">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Total Credits (Bank)</p><h3 class="text-3xl font-bold text-green-600">{{ fmt(totalBankCredit) }}</h3></div>
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center"><i class="fas fa-university text-white text-2xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow card-hover">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Total Credits (Cash)</p><h3 class="text-3xl font-bold text-green-600">{{ fmt(totalCashCredit) }}</h3></div>
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center"><i class="fas fa-money-bill-wave text-white text-2xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow card-hover">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Total SP Orders</p><h3 class="text-3xl font-bold text-red-600">{{ fmt(totalSpOrder) }}</h3></div>
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center"><i class="fas fa-shopping-cart text-white text-2xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow card-hover">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Current Balance</p><h3 class="text-3xl font-bold text-blue-600">{{ fmt(currentBalance) }}</h3></div>
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center"><i class="fas fa-balance-scale text-white text-2xl"></i></div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
