<script setup>
import { ref, onMounted } from 'vue';
import { getRunningLedger } from '../../api/customer';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const entries = ref([]);
const totalPaid = ref(0);

function fmt(n) {
  return Number(n || 0).toFixed(2);
}
function fmtDate(d) {
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

onMounted(async () => {
  const data = await getRunningLedger();
  entries.value = data.ledger_with_balance;
  totalPaid.value = data.total_paid;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-book mr-3 text-primary-600"></i>Running Ledger
      </h1>
      <p class="text-gray-600">Complete ledger for all your transactions</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else-if="entries.length" class="bg-white rounded-xl card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-gray-50">
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Description</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Debit</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Credit</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Balance</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="(item, i) in entries" :key="i" class="hover:bg-gray-50">
              <td class="py-4 px-6 text-gray-600">{{ fmtDate(item.date) }}</td>
              <td class="py-4 px-6">
                <span
                  class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                  :class="item.type === 'finance' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
                >{{ item.type === 'finance' ? 'Finance' : 'Old' }}</span>
              </td>
              <td class="py-4 px-6 text-gray-600">{{ item.description || '-' }}</td>
              <td class="py-4 px-6" :class="{ 'text-red-600 font-semibold': item.debit > 0 }">
                {{ item.debit > 0 ? `Rs. ${fmt(item.debit)}` : '' }}
              </td>
              <td class="py-4 px-6" :class="{ 'text-green-600 font-semibold': item.credit > 0 }">
                {{ item.credit > 0 ? `Rs. ${fmt(item.credit)}` : '' }}
              </td>
              <td class="py-4 px-6">
                <strong :class="item.running_balance > 0 ? 'text-red-600' : item.running_balance < 0 ? 'text-green-600' : 'text-gray-800'">
                  Rs. {{ fmt(item.running_balance) }}
                </strong>
              </td>
            </tr>
          </tbody>
          <tfoot class="bg-gray-50 border-t-2 border-gray-200">
            <tr>
              <td colspan="4" class="py-4 px-6 text-right text-lg font-bold text-gray-800">Total Paid:</td>
              <td class="py-4 px-6 text-lg font-bold text-green-600">Rs. {{ fmt(totalPaid) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>

    <div v-else class="bg-white rounded-xl card-shadow">
      <div class="p-12 text-center">
        <i class="fas fa-book fa-4x text-gray-300 mb-4"></i>
        <h4 class="text-xl font-semibold text-gray-500 mb-2">No Ledger Entries</h4>
        <p class="text-gray-400">You don't have any ledger entries yet.</p>
      </div>
    </div>
  </div>
</template>
