<script setup>
import { ref, onMounted } from 'vue';
import { listProductModels, deleteProductModel } from '../../api/manage';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const productModels = ref([]);

async function load() {
  const data = await listProductModels();
  productModels.value = data.results || data;
}

async function remove(pm) {
  if (!confirm(`Delete ${pm.model_name}? This may still be referenced by other records.`)) return;
  await deleteProductModel(pm.id);
  productModels.value = productModels.value.filter((p) => p.id !== pm.id);
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-cogs mr-3"></i>Product Models</h1>
        <p class="text-gray-600">Motorcycle product models</p>
      </div>
      <router-link
        :to="{ name: 'admin-manage-product-model-create' }"
        class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Add Product Model
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Model Name</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Make</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Engine Capacity</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">PCT Code</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Item Code</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pm in productModels" :key="pm.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ pm.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ pm.model_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ pm.make }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ pm.engine_capacity || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ pm.pct_code || '-' }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ pm.item_code || '-' }}</td>
              <td class="py-4 px-4">
                <div class="flex items-center space-x-2">
                  <router-link :to="{ name: 'admin-manage-product-model-edit', params: { id: pm.id } }" class="text-blue-600 hover:text-blue-800 transition" title="Edit">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button @click="remove(pm)" class="text-red-500 hover:text-red-700 transition" title="Delete">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!productModels.length">
              <td colspan="7" class="py-12 text-center text-gray-500">
                <i class="fas fa-cogs fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No product models found</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
