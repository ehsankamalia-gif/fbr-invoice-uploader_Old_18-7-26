<script setup>
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { getCustomerDetail } from '../../api/admin';
import { fmt, fmtDate } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const loading = ref(true);
const data = ref(null);

onMounted(async () => {
  data.value = await getCustomerDetail(route.params.id);
  loading.value = false;
});
</script>

<template>
  <div>
    <LoadingSpinner v-if="loading" />

    <template v-else-if="data">
      <div class="mb-8">
        <router-link :to="{ name: 'admin-customer-summary' }" class="text-blue-600 hover:text-blue-800 mb-4 inline-block">
          <i class="fas fa-arrow-left mr-2"></i>Back to Customer Summary
        </router-link>
        <router-link
          :to="{ name: 'admin-customer-ledger', params: { id: data.customer.id } }"
          class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-green-500 to-green-600 text-white font-medium rounded-lg hover:shadow-lg transition ml-4"
        >
          <i class="fas fa-book mr-2"></i>View Ledger
        </router-link>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-user mr-3"></i>{{ data.customer.name }}</h1>
        <p class="text-gray-600">Customer details and transaction history</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Phone Number</p><h3 class="text-xl font-bold text-gray-800">{{ data.customer.phone || '-' }}</h3></div>
            <div class="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center"><i class="fas fa-phone text-blue-600 text-xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">CNIC</p><h3 class="text-xl font-bold text-gray-800">{{ data.customer.cnic || '-' }}</h3></div>
            <div class="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center"><i class="fas fa-id-card text-purple-600 text-xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Total Credit</p><h3 class="text-xl font-bold text-purple-600">Rs. {{ fmt(data.total_credit) }}</h3></div>
            <div class="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center"><i class="fas fa-chart-pie text-purple-600 text-xl"></i></div>
          </div>
        </div>
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="flex items-center justify-between">
            <div><p class="text-sm text-gray-500 mb-1">Total Paid</p><h3 class="text-xl font-bold text-green-600">Rs. {{ fmt(data.total_paid) }}</h3></div>
            <div class="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center"><i class="fas fa-check-circle text-green-600 text-xl"></i></div>
          </div>
        </div>
      </div>

      <div class="mb-8">
        <h2 class="text-2xl font-bold text-gray-800 mb-4"><i class="fas fa-motorcycle mr-3 text-blue-600"></i>Credit Sales</h2>
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead>
                <tr class="border-b border-gray-200">
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Sale ID</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Chassis No</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit Price</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Remaining</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Sale Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(sale, i) in data.all_sales" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
                  <td class="py-4 px-4 text-sm text-gray-600">{{ sale.type }}</td>
                  <td class="py-4 px-4 text-sm text-gray-800">{{ sale.id }}</td>
                  <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ sale.sale_id || '-' }}</td>
                  <td class="py-4 px-4 text-sm text-gray-600">{{ sale.chassis_no || '-' }}</td>
                  <td class="py-4 px-4 text-sm font-semibold text-purple-600">Rs. {{ fmt(sale.credit_price) }}</td>
                  <td class="py-4 px-4 text-sm font-bold" :class="sale.remaining > 0 ? 'text-red-600' : 'text-green-600'">Rs. {{ fmt(sale.remaining) }}</td>
                  <td class="py-4 px-4">
                    <span
                      class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                      :class="{
                        'bg-green-100 text-green-800': sale.status === 'ACTIVE',
                        'bg-yellow-100 text-yellow-800': sale.status === 'OVERDUE',
                        'bg-gray-100 text-gray-800': !['ACTIVE', 'OVERDUE'].includes(sale.status),
                      }"
                    >{{ sale.status }}</span>
                  </td>
                  <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(sale.sale_date) }}</td>
                </tr>
                <tr v-if="!data.all_sales.length">
                  <td colspan="8" class="py-12 text-center text-gray-500">
                    <i class="fas fa-shopping-cart fa-3x mb-3 text-gray-300"></i>
                    <p class="text-lg">No credit sales found</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div>
        <h2 class="text-2xl font-bold text-gray-800 mb-4"><i class="fas fa-credit-card mr-3 text-green-600"></i>Payment History</h2>
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead>
                <tr class="border-b border-gray-200">
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Ledger ID</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Description</th>
                  <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(p, i) in data.all_payments" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
                  <td class="py-4 px-4 text-sm text-gray-600">{{ p.type }}</td>
                  <td class="py-4 px-4 text-sm text-gray-800">{{ p.ledger_id }}</td>
                  <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(p.date) }}</td>
                  <td class="py-4 px-4 text-sm text-gray-800">{{ p.description || '-' }}</td>
                  <td class="py-4 px-4 text-sm font-bold text-green-600">Rs. {{ fmt(p.amount) }}</td>
                </tr>
                <tr v-if="!data.all_payments.length">
                  <td colspan="5" class="py-12 text-center text-gray-500">
                    <i class="fas fa-credit-card fa-3x mb-3 text-gray-300"></i>
                    <p class="text-lg">No payments found</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
