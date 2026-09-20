<script setup>
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { getCustomerLedger } from '../../api/admin';
import { fmt, fmtDateTime } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const loading = ref(true);
const data = ref(null);

onMounted(async () => {
  data.value = await getCustomerLedger(route.params.id);
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-book mr-3"></i>Combined Ledger - {{ data.customer.name }}</h1>
        <p class="text-gray-600">Customer: {{ data.customer.phone || '-' }} | {{ data.customer.cnic || '-' }}</p>
      </div>

      <div class="bg-white rounded-xl p-6 card-shadow">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Description</th>
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Debit</th>
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit</th>
                <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Balance</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(t, i) in data.transactions" :key="i" class="border-b border-gray-100 hover:bg-gray-50">
                <td class="py-4 px-4 text-sm text-gray-800">{{ fmtDateTime(t.date) }}</td>
                <td class="py-4 px-4 text-sm text-gray-600">{{ t.type }}</td>
                <td class="py-4 px-4 text-sm text-gray-800">{{ t.description }}</td>
                <td class="py-4 px-4 text-sm font-semibold text-purple-600">{{ t.debit > 0 ? `Rs. ${fmt(t.debit)}` : '-' }}</td>
                <td class="py-4 px-4 text-sm font-semibold text-green-600">{{ t.credit > 0 ? `Rs. ${fmt(t.credit)}` : '-' }}</td>
                <td class="py-4 px-4 text-sm font-bold" :class="t.balance > 0 ? 'text-red-600' : 'text-green-600'">Rs. {{ fmt(t.balance) }}</td>
              </tr>
              <tr v-if="!data.transactions.length">
                <td colspan="6" class="py-12 text-center text-gray-500">
                  <i class="fas fa-book fa-3x mb-3 text-gray-300"></i>
                  <p class="text-lg">No transactions found</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
