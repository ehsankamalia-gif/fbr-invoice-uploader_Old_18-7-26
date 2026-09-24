<script setup>
import { ref, onMounted } from 'vue';
import { listInvoices } from '../../api/invoices';
import { useAuthStore } from '../../stores/auth';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';
import { fmt, fmtDateTime } from '../../utils/format';

const auth = useAuthStore();
const loading = ref(true);
const invoices = ref([]);
const search = ref('');

function statusClasses(status) {
  if (status === 'SYNCED') return 'bg-green-100 text-green-800';
  if (status === 'PENDING') return 'bg-yellow-100 text-yellow-800';
  return 'bg-red-100 text-red-800';
}

async function load() {
  loading.value = true;
  const data = await listInvoices(search.value);
  invoices.value = data;
  loading.value = false;
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-file-invoice mr-3"></i>Invoices</h1>
        <p class="text-gray-600">Sales invoices submitted to FBR</p>
      </div>
      <router-link
        v-if="auth.can('create_invoices')"
        :to="{ name: 'admin-invoice-create' }"
        class="inline-flex items-center px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Create Invoice
      </router-link>
    </div>

    <div class="mb-6">
      <input
        v-model="search" @keyup.enter="load" type="text" placeholder="Search by invoice number..."
        class="w-full sm:w-96 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
      />
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Invoice #</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Date</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Buyer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Chassis</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Total</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">FBR Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">FBR Invoice #</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in invoices" :key="inv.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ inv.invoice_number }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDateTime(inv.datetime) }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ inv.customer_name || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ inv.items?.[0]?.chassis_number || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">Rs. {{ fmt(inv.total_amount) }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                  :class="statusClasses(inv.sync_status)"
                  :title="inv.fbr_response_message || ''"
                >{{ inv.sync_status }}</span>
              </td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ inv.fbr_invoice_number || '-' }}</td>
            </tr>
            <tr v-if="!invoices.length">
              <td colspan="7" class="py-12 text-center text-gray-500">
                <i class="fas fa-file-invoice fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No invoices yet</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
