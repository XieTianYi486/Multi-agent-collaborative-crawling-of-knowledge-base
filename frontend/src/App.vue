<template>
  <!-- 统一注入 Element Plus 中文语言包（按需引入后不再 app.use(ElementPlus)） -->
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>

<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>
