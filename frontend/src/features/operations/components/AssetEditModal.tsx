import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Asset } from '@/types'
import type { AssetFilterOptions } from '@/api/operations'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { Button } from '@/components/ui/Button/Button'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'

const schema = z
  .object({
    name: z.string().trim().min(3).max(255),
    assetType: z.string().trim().min(1).max(100),
    category: z.string().trim().min(1).max(100),
    manufacturer: z.string().trim().min(1).max(100),
    model: z.string().trim().min(1).max(100),
    locationInFacility: z.string().trim().min(1).max(255),
    serialNumber: z.string().trim().min(1).max(100),
    installDate: z.string().min(1),
    commissionDate: z.string(),
    notes: z.string(),
  })
  .refine((values) => !values.commissionDate || values.commissionDate >= values.installDate, {
    path: ['commissionDate'],
    message: 'تاريخ التشغيل لا يمكن أن يسبق تاريخ التركيب',
  })

export type AssetEditValues = z.infer<typeof schema>

export function AssetEditModal({
  asset,
  open,
  onClose,
  onSave,
  saving,
  error,
  options,
}: {
  asset: Asset
  open: boolean
  onClose: () => void
  onSave: (values: AssetEditValues) => void
  saving: boolean
  error: Error | null
  options?: AssetFilterOptions
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AssetEditValues>({ resolver: zodResolver(schema) })
  useEffect(() => {
    if (open)
      reset({
        name: asset.name,
        assetType: asset.assetType ?? '',
        category: asset.category,
        manufacturer: asset.manufacturer ?? '',
        model: asset.model ?? '',
        locationInFacility: asset.locationInFacility,
        serialNumber: asset.serialNumber,
        installDate: asset.installDate.slice(0, 10),
        commissionDate: asset.commissionDate?.slice(0, 10) ?? '',
        notes: asset.notes,
      })
  }, [asset, open, reset])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="تعديل الأصل"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            إلغاء
          </Button>
          <Button loading={saving} onClick={handleSubmit(onSave)}>
            حفظ التعديلات
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSave)} noValidate>
        {error && <Alert tone="critical" title="تعذر حفظ التعديلات" description={error.message} />}
        <Field label="اسم الأصل" error={errors.name?.message} required>
          {(props) => <input {...props} {...register('name')} />}
        </Field>
        <FieldRow>
          <Field label="نوع الأصل" error={errors.assetType?.message} required>
            {(props) => (
              <>
                <input {...props} {...register('assetType')} list="edit-asset-types" />
                <datalist id="edit-asset-types">
                  {options?.assetTypes.map((value) => (
                    <option key={value} value={value} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
          <Field label="الفئة" error={errors.category?.message} required>
            {(props) => (
              <>
                <input {...props} {...register('category')} list="edit-asset-categories" />
                <datalist id="edit-asset-categories">
                  {options?.categories.map((value) => (
                    <option key={value} value={value} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
        </FieldRow>
        <FieldRow>
          <Field label="الشركة المصنعة" error={errors.manufacturer?.message} required>
            {(props) => <input {...props} {...register('manufacturer')} />}
          </Field>
          <Field label="الطراز" error={errors.model?.message} required>
            {(props) => <input {...props} {...register('model')} />}
          </Field>
        </FieldRow>
        <FieldRow>
          <Field label="الموقع" error={errors.locationInFacility?.message} required>
            {(props) => <input {...props} {...register('locationInFacility')} />}
          </Field>
          <Field label="الرقم التسلسلي" error={errors.serialNumber?.message} required>
            {(props) => <input {...props} {...register('serialNumber')} />}
          </Field>
        </FieldRow>
        <FieldRow>
          <Field label="تاريخ التركيب" error={errors.installDate?.message} required>
            {(props) => <input {...props} {...register('installDate')} type="date" />}
          </Field>
          <Field label="تاريخ التشغيل" error={errors.commissionDate?.message}>
            {(props) => <input {...props} {...register('commissionDate')} type="date" />}
          </Field>
        </FieldRow>
        <Field label="ملاحظات">
          {(props) => <textarea {...props} {...register('notes')} rows={3} />}
        </Field>
      </form>
    </Modal>
  )
}
