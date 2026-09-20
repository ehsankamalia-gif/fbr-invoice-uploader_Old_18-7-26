<script setup>
import { ref, onMounted } from 'vue';
import { listFinanceLedgerEntries, deleteFinanceLedgerEntry } from '../../api/manage';
import { fmt, fmtDate } from '../../utils/format';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const entries = ref([]);

async function load() {
  const data = await listFinanceLedgerEntries();
  entries.value = data.results || data;
}

async function remove(entry) {
  if (!confirm(`Delete ledger entry ${entry.ledger_id}?`)) return;
  await deleteFinanceLedgerEntry(entry.id);
  entries.value = entries.value.filter((e) => e.id !== entry.id);
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-book mr-3"></i>Finance Ledger</h1>
        <p class="text-gray-600">Raw finance ledger entries</p>
      </div>
      <router-link
        :to="{ name: 'admin-manage-finance-ledger-create' }"
        class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Add Ledger Entry
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Ledger ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Entry Type</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Debit</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Credit</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Balance</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in entries" :key="entry.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ entry.ledger_id }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ entry.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ entry.entry_type }}</td>
              <td class="py-4 px-4 text-sm text-red-600">{{ fmt(entry.debit) }}</td>
              <td class="py-4 px-4 text-sm text-green-600">{{ fmt(entry.credit) }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ fmt(entry.balance) }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(entry.entry_date) }}</td>
              <td class="py-4 px-4">
                <div class="flex items-center space-x-2">
                  <router-link :to="{ name: 'admin-manage-finance-ledger-edit', params: { id: entry.id } }" class="text-blue-600 hover:text-blue-800 transition" title="Edit">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button @click="remove(entry)" class="text-red-500 hover:text-red-700 transition" title="Delete">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!entries.length">
              <td colspan="8" class="py-12 text-center text-gray-500">
                <i class="fas fa-book fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No ledger entries found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
