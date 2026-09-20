<script setup>
import { ref, onMounted } from 'vue';
import { getTransactions } from '../../api/admin';
import { fmtDateTime } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const entries = ref([]);

onMounted(async () => {
  const data = await getTransactions();
  entries.value = data.ledger_entries;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-history mr-3"></i>Transaction History</h1>
      <p class="text-gray-600">Complete audit trail of all financial transactions</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Ledger ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Entry Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Debit</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Balance</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in entries" :key="entry.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ entry.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ entry.ledger_id }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ entry.customer_name }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                  :class="entry.entry_type === 'DEBIT' ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'"
                >{{ entry.entry_type }}</span>
              </td>
              <td class="py-4 px-4 text-sm font-bold" :class="entry.debit > 0 ? 'text-red-600' : 'text-gray-400'">
                {{ entry.debit > 0 ? `Rs. ${entry.debit}` : '-' }}
              </td>
              <td class="py-4 px-4 text-sm font-bold" :class="entry.credit > 0 ? 'text-green-600' : 'text-gray-400'">
                {{ entry.credit > 0 ? `Rs. ${entry.credit}` : '-' }}
              </td>
              <td class="py-4 px-4 text-sm font-bold text-gray-800">Rs. {{ entry.balance }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDateTime(entry.date) }}</td>
            </tr>
            <tr v-if="!entries.length">
              <td colspan="8" class="py-12 text-center text-gray-500">
                <i class="fas fa-history fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No transactions found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
