<script setup>
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { getLoanDetail } from '../../api/customer';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const loading = ref(true);
const data = ref(null);

function fmt(n) {
  return Number(n || 0).toFixed(2);
}
function fmtDate(d) {
  if (!d) return 'N/A';
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

onMounted(async () => {
  data.value = await getLoanDetail(route.params.loanType, route.params.loanId);
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <nav class="flex items-center text-sm text-gray-500 mb-4">
        <router-link :to="{ name: 'customer-dashboard' }" class="text-primary-600 hover:text-primary-700">Dashboard</router-link>
        <i class="fas fa-chevron-right mx-2 text-gray-300"></i>
        <span class="text-gray-700">Loan Details</span>
      </nav>
      <h1 v-if="data" class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-info-circle mr-3 text-primary-600"></i>Loan Information
        <span class="ml-4 text-lg">
          <span
            class="inline-flex items-center px-4 py-1 rounded-full text-sm font-medium"
            :class="data.loan_type === 'finance' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
          >{{ data.loan_type === 'finance' ? 'Finance' : 'Old' }}</span>
        </span>
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <template v-else-if="data">
      <div class="bg-white rounded-xl p-6 card-shadow mb-6">
        <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
          <i class="fas fa-file-alt mr-3 text-primary-500"></i>Loan Information
        </h5>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div>
            <label class="text-sm text-gray-500 block mb-1">Sale ID</label>
            <p class="text-gray-800 font-semibold">{{ data.loan.sale_id }}</p>
          </div>
          <div>
            <label class="text-sm text-gray-500 block mb-1">Status</label>
            <p class="text-gray-800">
              <span
                class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                :class="{
                  'bg-green-100 text-green-800': data.loan_status === 'ACTIVE',
                  'bg-yellow-100 text-yellow-800': data.loan_status === 'OVERDUE',
                  'bg-gray-100 text-gray-800': !['ACTIVE', 'OVERDUE'].includes(data.loan_status),
                }"
              >
                <i v-if="data.loan_status === 'ACTIVE'" class="fas fa-check-circle mr-1"></i>
                <i v-else-if="data.loan_status === 'OVERDUE'" class="fas fa-exclamation-circle mr-1"></i>
                {{ data.loan_status.charAt(0) + data.loan_status.slice(1).toLowerCase() }}
              </span>
            </p>
          </div>
          <div>
            <label class="text-sm text-gray-500 block mb-1">Color</label>
            <p class="text-gray-800">{{ data.motorcycle_color || 'N/A' }}</p>
          </div>
          <div>
            <label class="text-sm text-gray-500 block mb-1">Chassis Number</label>
            <p class="text-gray-800 font-mono">{{ data.chassis_no || 'N/A' }}</p>
          </div>
          <div>
            <label class="text-sm text-gray-500 block mb-1">Engine Number</label>
            <p class="text-gray-800 font-mono">{{ data.motorcycle_engine_no || 'N/A' }}</p>
          </div>
          <div>
            <label class="text-sm text-gray-500 block mb-1">Sale Date</label>
            <p class="text-gray-800">{{ fmtDate(data.loan.sale_date) }}</p>
          </div>
          <div v-if="data.loan_type === 'finance'">
            <label class="text-sm text-gray-500 block mb-1">Due Date</label>
            <p class="text-gray-800">{{ fmtDate(data.loan.due_date) }}</p>
          </div>
        </div>

        <div class="mt-6 pt-6 border-t border-gray-200">
          <h6 class="text-md font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-money-bill-wave mr-2 text-green-500"></i>Financial Details
          </h6>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div class="bg-gray-50 rounded-xl p-4 text-center">
              <label class="text-sm text-gray-500 block mb-1">Total Amount</label>
              <h4 class="text-xl font-bold text-gray-800">Rs. {{ fmt(data.loan.total_price) }}</h4>
            </div>
            <div class="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
              <label class="text-sm text-red-700 block mb-1">Remaining Balance</label>
              <h4 class="text-xl font-bold text-red-800">Rs. {{ fmt(data.loan.remaining) }}</h4>
            </div>
          </div>

          <template v-if="data.loan_type === 'finance'">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div class="bg-gray-50 rounded-xl p-4 text-center">
                <label class="text-sm text-gray-500 block mb-1">Cash Price</label>
                <h4 class="text-xl font-bold text-gray-800">Rs. {{ fmt(data.loan.cash_price) }}</h4>
              </div>
              <div class="bg-gray-50 rounded-xl p-4 text-center">
                <label class="text-sm text-gray-500 block mb-1">Credit Price</label>
                <h4 class="text-xl font-bold text-gray-800">Rs. {{ fmt(data.loan.credit_price) }}</h4>
              </div>
              <div class="bg-gray-50 rounded-xl p-4 text-center">
                <label class="text-sm text-gray-500 block mb-1">Down Payment</label>
                <h4 class="text-xl font-bold text-gray-800">Rs. {{ fmt(data.loan.down_payment) }}</h4>
              </div>
            </div>
            <div class="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-center">
              <label class="text-sm text-yellow-700 block mb-1">Installment Amount</label>
              <h4 class="text-xl font-bold text-yellow-800">Rs. {{ fmt(data.loan.installment_amount) }}</h4>
              <p class="text-sm text-yellow-600 mt-1">
                Duration: {{ data.loan.duration_months }} months {{ data.loan.duration_days }} days
              </p>
            </div>
          </template>
        </div>
      </div>

      <div v-if="data.payment_entries.length" class="bg-white rounded-xl card-shadow mb-6">
        <div class="p-6 border-b border-gray-200">
          <h5 class="text-lg font-semibold text-gray-800 flex items-center">
            <i class="fas fa-history mr-3 text-blue-500"></i>Payment History
          </h5>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50">
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Date</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Description</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Amount Paid</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <tr v-for="(entry, i) in data.payment_entries" :key="i" class="hover:bg-gray-50">
                <td class="py-4 px-6 text-gray-600">{{ fmtDate(entry.date) }}</td>
                <td class="py-4 px-6 text-gray-800">{{ entry.description || '-' }}</td>
                <td class="py-4 px-6"><strong class="text-green-600 text-lg">Rs. {{ fmt(entry.amount) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="data.ledger_with_balance.length" class="bg-white rounded-xl card-shadow">
        <div class="p-6 border-b border-gray-200">
          <h5 class="text-lg font-semibold text-gray-800 flex items-center">
            <i class="fas fa-book mr-3 text-gray-500"></i>Transaction Ledger
          </h5>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-gray-50">
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Date</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Description</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Debit</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Credit</th>
                <th class="text-left py-4 px-6 text-sm font-semibold text-gray-600">Balance</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <tr v-for="(item, i) in data.ledger_with_balance" :key="i" class="hover:bg-gray-50">
                <td class="py-4 px-6 text-gray-600">{{ fmtDate(item.date) }}</td>
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
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
