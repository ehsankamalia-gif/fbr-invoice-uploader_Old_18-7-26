<script setup>
import { ref, onMounted } from 'vue';
import { getPayments } from '../../api/customer';
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
  const data = await getPayments();
  entries.value = data.payment_entries;
  totalPaid.value = data.total_paid;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-history mr-3 text-primary-600"></i>Payment History
      </h1>
      <p class="text-gray-600">View all your installment payments</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else-if="entries.length" class="bg-white rounded-xl card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-gray-50">
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Chassis No</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Description</th>
              <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Amount Paid</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="(p, i) in entries" :key="i" class="hover:bg-gray-50">
              <td class="py-4 px-6">
                <span
                  class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                  :class="p.type === 'finance' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
                >{{ p.type === 'finance' ? 'Finance' : 'Old' }}</span>
              </td>
              <td class="py-4 px-6"><code class="text-gray-700 bg-gray-100 px-2 py-1 rounded">{{ p.chassis_no }}</code></td>
              <td class="py-4 px-6 text-gray-600">{{ fmtDate(p.date) }}</td>
              <td class="py-4 px-6 text-gray-800">{{ p.description || '-' }}</td>
              <td class="py-4 px-6"><strong class="text-green-600 text-lg">Rs. {{ fmt(p.amount) }}</strong></td>
            </tr>
          </tbody>
          <tfoot class="bg-gray-50 border-t-2 border-gray-200">
            <tr>
              <td colspan="4" class="py-4 px-6 text-right text-lg font-bold text-gray-800">Total Paid:</td>
              <td class="py-4 px-6 text-lg font-bold text-green-600">Rs. {{ fmt(totalPaid) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>

    <div v-else class="bg-white rounded-xl card-shadow">
      <div class="p-12 text-center">
        <i class="fas fa-credit-card fa-4x text-gray-300 mb-4"></i>
        <h4 class="text-xl font-semibold text-gray-500 mb-2">No Payments Found</h4>
        <p class="text-gray-400">You don't have any payment records yet.</p>
      </div>
    </div>
  </div>
</template>
