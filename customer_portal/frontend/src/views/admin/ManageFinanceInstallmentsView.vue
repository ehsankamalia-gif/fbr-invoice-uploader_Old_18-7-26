<script setup>
import { ref, onMounted } from 'vue';
import { listFinanceInstallments, deleteFinanceInstallment } from '../../api/manage';
import StatusBadge from '../../components/ui/StatusBadge.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';
import { fmt, fmtDate } from '../../utils/format';

const loading = ref(true);
const installments = ref([]);

async function load() {
  const data = await listFinanceInstallments();
  installments.value = data.results || data;
}

async function remove(inst) {
  if (!confirm(`Delete installment ${inst.payment_id}?`)) return;
  await deleteFinanceInstallment(inst.id);
  installments.value = installments.value.filter((i) => i.id !== inst.id);
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-hand-holding-usd mr-3"></i>Finance Installments</h1>
        <p class="text-gray-600">Finance installment schedule entries</p>
      </div>
      <router-link
        :to="{ name: 'admin-manage-finance-installment-create' }"
        class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Add Installment
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Payment ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Customer</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Sale</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Paid Amount</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Payment Date</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inst in installments" :key="inst.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ inst.payment_id }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ inst.customer_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ inst.sale_label || '-' }}</td>
              <td class="py-4 px-4 text-sm font-bold text-green-600">Rs. {{ fmt(inst.paid_amount) }}</td>
              <td class="py-4 px-4"><StatusBadge :status="inst.status" /></td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ fmtDate(inst.payment_date) }}</td>
              <td class="py-4 px-4">
                <div class="flex items-center space-x-2">
                  <router-link :to="{ name: 'admin-manage-finance-installment-edit', params: { id: inst.id } }" class="text-blue-600 hover:text-blue-800 transition" title="Edit">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button @click="remove(inst)" class="text-red-500 hover:text-red-700 transition" title="Delete">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!installments.length">
              <td colspan="7" class="py-12 text-center text-gray-500">
                <i class="fas fa-hand-holding-usd fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No installments found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
