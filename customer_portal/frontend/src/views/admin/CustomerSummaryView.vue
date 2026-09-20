<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { getCustomerSummary } from '../../api/admin';
import { fmt } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const customers = ref([]);
const search = ref('');
let debounceHandle = null;

async function load() {
  const data = await getCustomerSummary(search.value);
  customers.value = data.customers;
}

function onSearchInput() {
  clearTimeout(debounceHandle);
  debounceHandle = setTimeout(load, 300);
}

function ledgerBadgeClass(type) {
  if (type === 'Combined') return 'bg-purple-100 text-purple-800';
  if (type === 'Finance') return 'bg-green-100 text-green-800';
  return 'bg-yellow-100 text-yellow-800';
}

onMounted(async () => {
  await load();
  loading.value = false;
});
onBeforeUnmount(() => clearTimeout(debounceHandle));
</script>

<template>
  <div>
    <div class="mb-8">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-users mr-3"></i>Customer Summary</h1>
          <p class="text-gray-600">Customer credit summary with bike counts</p>
        </div>
        <div class="flex gap-3 w-full sm:w-auto">
          <input
            v-model="search"
            @input="onSearchInput"
            type="text"
            placeholder="Search by name, phone, or CNIC..."
            class="flex-1 sm:w-64 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            v-if="search"
            @click="search = ''; load()"
            class="inline-flex items-center px-4 py-2 bg-gray-500 text-white font-medium rounded-lg hover:bg-gray-600 transition"
          >
            <i class="fas fa-times mr-2"></i>Clear
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
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer Name</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Ledger Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Phone Number</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Total Bikes</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Total Credit</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Total Paid</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Remaining</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in customers" :key="item.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ item.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">
                <router-link :to="{ name: 'admin-customer-detail', params: { id: item.id } }" class="text-blue-600 hover:text-blue-800 transition">
                  {{ item.name }}
                </router-link>
              </td>
              <td class="py-4 px-4">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium" :class="ledgerBadgeClass(item.ledger_type)">
                  {{ item.ledger_type }}
                </span>
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ item.phone }}</td>
              <td class="py-4 px-4 text-sm font-bold text-blue-600">{{ item.total_bikes }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-purple-600">Rs. {{ fmt(item.total_credit) }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-green-600">Rs. {{ fmt(item.total_paid) }}</td>
              <td class="py-4 px-4 text-sm font-semibold" :class="item.total_remaining > 0 ? 'text-red-600' : 'text-green-600'">
                Rs. {{ fmt(item.total_remaining) }}
              </td>
              <td class="py-4 px-4">
                <router-link :to="{ name: 'admin-customer-detail', params: { id: item.id } }" class="text-blue-600 hover:text-blue-800 mr-3">
                  <i class="fas fa-eye"></i>
                </router-link>
                <router-link :to="{ name: 'admin-customer-ledger', params: { id: item.id } }" class="text-green-600 hover:text-green-800">
                  <i class="fas fa-book"></i>
                </router-link>
              </td>
            </tr>
            <tr v-if="!customers.length">
              <td colspan="9" class="py-12 text-center text-gray-500">
                <i class="fas fa-users fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No customers found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
