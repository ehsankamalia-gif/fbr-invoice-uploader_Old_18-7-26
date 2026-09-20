<script setup>
import { ref, onMounted } from 'vue';
import { listManageCustomers, toggleCustomerDeleted } from '../../api/manage';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const customers = ref([]);
const search = ref('');
let debounceHandle = null;

async function load() {
  customers.value = await listManageCustomers(search.value);
}

function onSearchInput() {
  clearTimeout(debounceHandle);
  debounceHandle = setTimeout(load, 300);
}

async function toggleDeleted(customer) {
  const verb = customer.is_deleted ? 'restore' : 'delete';
  if (!confirm(`Are you sure you want to ${verb} ${customer.name}?`)) return;
  const updated = await toggleCustomerDeleted(customer.id);
  const idx = customers.value.findIndex((c) => c.id === customer.id);
  if (idx !== -1) customers.value[idx] = updated;
}

onMounted(async () => {
  await load();
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-address-book mr-3"></i>Manage Customers</h1>
        <p class="text-gray-600">All customer records</p>
      </div>
      <div class="flex gap-3">
        <input
          v-model="search"
          @input="onSearchInput"
          type="text"
          placeholder="Search name, CNIC, phone..."
          class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
        />
        <router-link
          :to="{ name: 'admin-manage-customer-create' }"
          class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
        >
          <i class="fas fa-plus mr-2"></i>Add Customer
        </router-link>
      </div>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Name</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">CNIC</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Phone</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="customer in customers" :key="customer.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ customer.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ customer.name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ customer.cnic }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ customer.phone || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ customer.type }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                  :class="customer.is_deleted ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'"
                >{{ customer.is_deleted ? 'Deleted' : 'Active' }}</span>
              </td>
              <td class="py-4 px-4">
                <div class="flex items-center space-x-2">
                  <router-link :to="{ name: 'admin-manage-customer-edit', params: { id: customer.id } }" class="text-blue-600 hover:text-blue-800 transition" title="Edit">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button
                    @click="toggleDeleted(customer)"
                    :class="customer.is_deleted ? 'text-green-600 hover:text-green-800' : 'text-red-500 hover:text-red-700'"
                    class="transition"
                    :title="customer.is_deleted ? 'Restore' : 'Delete'"
                  >
                    <i class="fas" :class="customer.is_deleted ? 'fa-undo' : 'fa-trash'"></i>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!customers.length">
              <td colspan="7" class="py-12 text-center text-gray-500">
                <i class="fas fa-address-book fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No customers found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
