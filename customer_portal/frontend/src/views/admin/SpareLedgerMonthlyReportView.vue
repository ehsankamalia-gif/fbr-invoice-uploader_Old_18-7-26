<script setup>
import { ref, onMounted, computed } from 'vue';
import { getSpareLedgerMonthlyReport } from '../../api/admin';
import { fmt } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const reportData = ref([]);
const grandTotalIn = ref(0);
const grandTotalOut = ref(0);
const overallBalance = ref(0);

const sumBankCredit = computed(() => reportData.value.reduce((s, r) => s + r.bank_credit, 0));
const sumCashCredit = computed(() => reportData.value.reduce((s, r) => s + r.hard_cash_credit, 0));
const sumBankDebit = computed(() => reportData.value.reduce((s, r) => s + r.bank_debit, 0));
const sumCashDebit = computed(() => reportData.value.reduce((s, r) => s + r.hard_cash_debit, 0));

onMounted(async () => {
  const data = await getSpareLedgerMonthlyReport();
  reportData.value = data.report_data;
  grandTotalIn.value = data.grand_total_in;
  grandTotalOut.value = data.grand_total_out;
  overallBalance.value = data.overall_balance;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-calendar-alt mr-3"></i>Spare Parts Ledger - Monthly Report</h1>
      <p class="text-gray-600">Monthly report with detailed cash type breakdown and balances</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="bg-white rounded-xl p-6 card-shadow">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Month</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">B/F</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Bank Credit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Hard Cash Credit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Total Credit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Bank Debit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Hard Cash Debit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Total Debit</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">Closing Balance</th>
                <th class="text-left py-3 px-2 text-sm font-semibold text-gray-700">C/F</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in reportData" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-3 px-2 text-sm font-semibold text-gray-800">{{ row.month_key }}</td>
                <td class="py-3 px-2 text-sm text-gray-600">{{ fmt(row.brought_forward) }}</td>
                <td class="py-3 px-2 text-sm text-green-600">{{ fmt(row.bank_credit) }}</td>
                <td class="py-3 px-2 text-sm text-green-600">{{ fmt(row.hard_cash_credit) }}</td>
                <td class="py-3 px-2 text-sm font-semibold text-green-600">{{ fmt(row.total_credit) }}</td>
                <td class="py-3 px-2 text-sm text-red-600">{{ fmt(row.bank_debit) }}</td>
                <td class="py-3 px-2 text-sm text-red-600">{{ fmt(row.hard_cash_debit) }}</td>
                <td class="py-3 px-2 text-sm font-semibold text-red-600">{{ fmt(row.total_debit) }}</td>
                <td class="py-3 px-2 text-sm font-bold text-blue-600">{{ fmt(row.closing_balance) }}</td>
                <td class="py-3 px-2 text-sm text-gray-600">{{ fmt(row.carried_forward) }}</td>
              </tr>
              <tr v-if="!reportData.length">
                <td colspan="10" class="py-8 text-center text-gray-500">
                  <i class="fas fa-calendar-times fa-2x mb-2"></i>
                  <p>No monthly report data available</p>
                </td>
              </tr>
              <tr v-if="reportData.length" class="bg-gray-50 border-t-2 border-gray-300 font-bold">
                <td class="py-3 px-2 text-sm text-gray-800">Grand Total</td>
                <td class="py-3 px-2 text-sm text-gray-600">-</td>
                <td class="py-3 px-2 text-sm text-green-600">{{ fmt(sumBankCredit) }}</td>
                <td class="py-3 px-2 text-sm text-green-600">{{ fmt(sumCashCredit) }}</td>
                <td class="py-3 px-2 text-sm text-green-600">{{ fmt(grandTotalIn) }}</td>
                <td class="py-3 px-2 text-sm text-red-600">{{ fmt(sumBankDebit) }}</td>
                <td class="py-3 px-2 text-sm text-red-600">{{ fmt(sumCashDebit) }}</td>
                <td class="py-3 px-2 text-sm text-red-600">{{ fmt(grandTotalOut) }}</td>
                <td class="py-3 px-2 text-sm text-blue-600">{{ fmt(overallBalance) }}</td>
                <td class="py-3 px-2 text-sm text-gray-600">-</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="reportData.length" class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
        <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-green-500">
          <h3 class="text-sm text-gray-600 font-semibold mb-2">Total Credits</h3>
          <p class="text-3xl font-bold text-green-600">{{ fmt(grandTotalIn) }}</p>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-red-500">
          <h3 class="text-sm text-gray-600 font-semibold mb-2">Total Debits</h3>
          <p class="text-3xl font-bold text-red-600">{{ fmt(grandTotalOut) }}</p>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow card-hover border-l-4 border-blue-500">
          <h3 class="text-sm text-gray-600 font-semibold mb-2">Overall Balance</h3>
          <p class="text-3xl font-bold text-blue-600">{{ fmt(overallBalance) }}</p>
        </div>
      </div>
    </template>
  </div>
</template>
