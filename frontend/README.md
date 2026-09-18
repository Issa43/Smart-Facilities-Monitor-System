# نُظم — منصة إدارة دورة حياة المنشآت

واجهة SFLMS العربية المبنية بـ React وTypeScript وVite، والمتصلة بخلفية Django الحقيقية عبر JWT. لا توجد حسابات أو كلمات مرور تجريبية في الواجهة، ولا تستخدم نسخة الإنتاج بيانات fixtures أو نجاحات محلية وهمية.

## المتطلبات

- Node.js 22 LTS وnpm
- خلفية SFLMS العاملة على `http://localhost:8000`
- حساب مستخدم حقيقي فعّال في قاعدة البيانات

## الإعداد

انسخ `.env.example` إلى `.env` عند الحاجة. الإعداد الافتراضي:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_ENABLE_DEMO_DATA=false
```

يجب إبقاء `VITE_ENABLE_DEMO_DATA=false` لأي تشغيل متصل أو إنتاجي. كود fixtures القديم معزول خلف وضع تطوير صريح ولا يُستخدم تلقائياً عند فشل API.

## تشغيل الخلفية

من مجلد backend:

```powershell
docker compose up -d --build
docker compose exec backend python manage.py createsuperuser
```

الأمر الثاني مطلوب مرة واحدة فقط إذا لم يوجد حساب Super Admin. الخلفية: `http://localhost:8000`، ووثائق API: `http://localhost:8000/api/docs/`.

## تشغيل الواجهة

من هذا المجلد:

```powershell
npm install
npm run dev
```

افتح `http://localhost:5173` وسجّل الدخول بالبريد الإلكتروني وكلمة المرور لحساب حقيقي.

## فحوص الجودة

```powershell
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build
```

اختبارات E2E تستخدم Playwright وبيئة Docker معزولة باسم `sflms-e2e`.
كلمة مرور مستخدمي الاختبار تُمرر عبر `E2E_TEST_PASSWORD` فقط، ويجب حذف
الحاويات والأحجام الخاصة بهذه البيئة بعد الاختبار. لا تُستخدم حسابات حقيقية.

## صورة الإنتاج

يبني `Dockerfile` الواجهة ثم يخدمها عبر Nginx، ويوجه `/api/` إلى خدمة backend.
تُستخدم الصورة من `docker-compose.production.yml` في مستودع الخلفية مع
`IMAGE_TAG` إلزامي. تبقى الوسائط المحمية خلف نقاط تنزيل Django الموثقة ولا
تُركب داخل حاوية Nginx. إنهاء TLS والنطاق وشهادات HTTPS قرارات نشر خارجية.

## حالة التكامل

راجع [مصفوفة تكامل الواجهة والخلفية](docs/REAL_BACKEND_INTEGRATION_MATRIX.md) لمعرفة حالة كل مسار، نقاط API المتصلة، وفجوات API/domain التي أبقت واجهاتها ظاهرة من دون اختلاق بيانات أو خدمات.

الوظائف المتصلة تشمل المصادقة والملف الشخصي والمستخدمين والمشاريع ودورات حياة المشاريع والمنشآت والأصول وأوامر الصيانة والأعطال والتنبيهات والحوادث والأدلة المحمية والتقارير غير المتزامنة. الوظائف التي لا يوفّر لها backend عقداً حالياً تعرض خطأ أو حالة «غير مدعوم» صريحة.
