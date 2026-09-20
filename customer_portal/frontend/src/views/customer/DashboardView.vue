<script setup>
import { ref, onMounted } from 'vue';
import { getDashboard } from '../../api/customer';
import StatCard from '../../components/ui/StatCard.vue';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const activeLoans = ref([]);
const closedLoans = ref([]);
const totalOutstanding = ref(0);
const totalPaid = ref(0);

function fmt(n) {
  return Number(n || 0).toFixed(2);
}
function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

onMounted(async () => {
  const data = await getDashboard();
  activeLoans.value = data.active_loans;
  closedLoans.value = data.closed_loans;
  totalOutstanding.value = data.total_outstanding;
  totalPaid.value = data.total_paid;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-tachometer-alt mr-3 text-primary-600"></i>My Dashboard
      </h1>
      <p class="text-gray-600">Overview of your motorcycle loans and payments</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <template v-else>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard label="Active Loans" :value="activeLoans.length" icon="fas fa-motorcycle" gradient="from-primary-500 to-primary-600" />
        <StatCard label="Outstanding Balance" :value="`Rs. ${fmt(totalOutstanding)}`" icon="fas fa-wallet" gradient="from-red-500 to-red-600" value-class="text-red-600" />
        <StatCard label="Total Paid" :value="`Rs. ${fmt(totalPaid)}`" icon="fas fa-check-circle" gradient="from-green-500 to-green-600" value-class="text-green-600" />
      </div>

      <div v-if="activeLoans.length" class="bg-white rounded-xl card-shadow mb-8">
        <div class="p-6 border-b border-gray-200">
          <h5 class="text-lg font-semibold text-gray-800 flex items-center">
            <i class="fas fa-motorcycle mr-3 text-primary-500"></i>Active Loans
          </h5>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50">
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Type</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Chassis No.</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Total Amount</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Paid</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Remaining</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Status</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <tr v-for="loan in activeLoans" :key="`${loan.type}-${loan.id}`" class="hover:bg-gray-50">
                <td class="py-4 px-6">
                  <span
                    class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                    :class="loan.type === 'finance' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
                  >{{ loan.type === 'finance' ? 'Finance' : 'Old' }}</span>
                </td>
                <td class="py-4 px-6"><code class="text-primary-600 bg-primary-50 px-2 py-1 rounded">{{ loan.chassis_no }}</code></td>
                <td class="py-4 px-6 text-gray-800">Rs. {{ fmt(loan.total_price) }}</td>
                <td class="py-4 px-6 text-green-600">Rs. {{ fmt(loan.paid) }}</td>
                <td class="py-4 px-6"><strong class="text-red-600">Rs. {{ fmt(loan.remaining) }}</strong></td>
                <td class="py-4 px-6"><StatusBadge :status="loan.status" /></td>
                <td class="py-4 px-6">
                  <router-link
                    :to="{ name: 'customer-loan-detail', params: { loanType: loan.type, loanId: loan.id } }"
                    class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-primary-500 to-primary-600 text-white text-sm font-medium rounded-lg hover:shadow-lg transition"
                  >
                    <i class="fas fa-eye mr-2"></i>View
                  </router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="closedLoans.length" class="bg-white rounded-xl card-shadow">
        <div class="p-6 border-b border-gray-200">
          <h5 class="text-lg font-semibold text-gray-800 flex items-center">
            <i class="fas fa-history mr-3 text-gray-500"></i>Recently Closed Loans
          </h5>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50">
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Type</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Chassis No.</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Sale Date</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Total Amount</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <tr v-for="loan in closedLoans" :key="`${loan.type}-${loan.id}`" class="hover:bg-gray-50">
                <td class="py-4 px-6">
                  <span
                    class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                    :class="loan.type === 'finance' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
                  >{{ loan.type === 'finance' ? 'Finance' : 'Old' }}</span>
                </td>
                <td class="py-4 px-6"><code class="text-gray-500 bg-gray-100 px-2 py-1 rounded">{{ loan.chassis_no }}</code></td>
                <td class="py-4 px-6 text-gray-600">{{ fmtDate(loan.sale_date) }}</td>
                <td class="py-4 px-6 text-gray-800">Rs. {{ fmt(loan.total_price) }}</td>
                <td class="py-4 px-6">
                  <router-link
                    :to="{ name: 'customer-loan-detail', params: { loanType: loan.type, loanId: loan.id } }"
                    class="inline-flex items-center px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition"
                  >
                    <i class="fas fa-eye mr-2"></i>View
                  </router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="!activeLoans.length && !closedLoans.length" class="bg-white rounded-xl card-shadow">
        <div class="p-12 text-center">
          <i class="fas fa-inbox fa-4x text-gray-300 mb-4"></i>
          <h4 class="text-xl font-semibold text-gray-500 mb-2">No Loans Found</h4>
          <p class="text-gray-400">You don't have any active or closed loans at the moment.</p>
        </div>
      </div>
    </template>
  </div>
</template>
