<script setup>
import { ref, onMounted } from 'vue';
import { getInventory } from '../../api/admin';
import { deleteMotorcycle } from '../../api/manage';
import { useAuthStore } from '../../stores/auth';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const auth = useAuthStore();
const loading = ref(true);
const motorcycles = ref([]);

async function load() {
  const data = await getInventory();
  motorcycles.value = data.motorcycles;
}

async function remove(bike) {
  if (!confirm(`Delete ${bike.chassis_number}? This may still be referenced by other records.`)) return;
  await deleteMotorcycle(bike.id);
  motorcycles.value = motorcycles.value.filter((m) => m.id !== bike.id);
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
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-motorcycle mr-3"></i>Inventory</h1>
        <p class="text-gray-600">Manage motorcycle inventory</p>
      </div>
      <router-link
        v-if="auth.can('manage_inventory')"
        :to="{ name: 'admin-manage-motorcycle-create' }"
        class="inline-flex items-center px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:shadow-lg transition"
      >
        <i class="fas fa-plus mr-2"></i>Add Motorcycle
      </router-link>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-6 card-shadow">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">ID</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Chassis No</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Engine No</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Model</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Color</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Status</th>
              <th class="text-left py-4 px-4 text-sm font-semibold text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bike in motorcycles" :key="bike.id" class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-4 px-4 text-sm text-gray-800">{{ bike.id }}</td>
              <td class="py-4 px-4 text-sm font-semibold text-gray-800">{{ bike.chassis_number }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ bike.engine_number }}</td>
              <td class="py-4 px-4 text-sm text-gray-800">{{ bike.model_name }}</td>
              <td class="py-4 px-4 text-sm text-gray-600">{{ bike.color }}</td>
              <td class="py-4 px-4">
                <span
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                  :class="bike.status === 'IN_STOCK' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                >{{ bike.status }}</span>
              </td>
              <td class="py-4 px-4">
                <template v-if="auth.can('manage_inventory')">
                  <router-link :to="{ name: 'admin-manage-motorcycle-edit', params: { id: bike.id } }" class="text-blue-600 hover:text-blue-800 transition mr-3">
                    <i class="fas fa-edit"></i>
                  </router-link>
                  <button @click="remove(bike)" class="text-red-500 hover:text-red-700 transition">
                    <i class="fas fa-trash"></i>
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="!motorcycles.length">
              <td colspan="7" class="py-12 text-center text-gray-500">
                <i class="fas fa-motorcycle fa-3x mb-3 text-gray-300"></i>
                <p class="text-lg">No motorcycles in inventory</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
