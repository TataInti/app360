import { renderHook, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import useForm from './useForm'

describe('useForm', () => {
  it('initializes with correct values', () => {
    const { result } = renderHook(() => useForm({ name: '', email: '' }))

    expect(result.current.values).toEqual({ name: '', email: '' })
    expect(result.current.errors).toEqual({})
    expect(result.current.isSubmitting).toBe(false)
  })

  it('handles input changes', () => {
    const { result } = renderHook(() => useForm({ name: '' }))

    act(() => {
      result.current.handleChange('name')({ target: { value: 'John' } })
    })

    expect(result.current.values.name).toBe('John')
  })

  it('validates form on submit', async () => {
    const validate = (values) => {
      const errors = {}
      if (!values.name) errors.name = 'Name is required'
      return errors
    }

    const onSubmit = vi.fn()
    const { result } = renderHook(() => useForm({ name: '' }, validate))

    await act(async () => {
      await result.current.handleSubmit(onSubmit)
    })

    expect(result.current.errors.name).toBe('Name is required')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('calls onSubmit when validation passes', async () => {
    const onSubmit = vi.fn()
    const { result } = renderHook(() => useForm({ name: 'John' }))

    await act(async () => {
      await result.current.handleSubmit(onSubmit)
    })

    expect(onSubmit).toHaveBeenCalledWith({ name: 'John' })
  })
})