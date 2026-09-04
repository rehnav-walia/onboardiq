import FieldError from '../FieldError.jsx';
import { ACCOUNT_TYPES } from '../../validation.js';

export default function StepAccountType({ values, errors, touched, onChange }) {
  return (
    <fieldset className="form-step">
      <legend>Account Type</legend>

      <div className="form-field">
        <label htmlFor="account_type">Account type</label>
        <select
          id="account_type"
          name="account_type"
          value={values.account_type}
          onChange={(e) => onChange('account_type', e.target.value)}
          aria-invalid={Boolean(touched.account_type && errors.account_type)}
        >
          <option value="">Select an account type…</option>
          {ACCOUNT_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        <FieldError message={touched.account_type ? errors.account_type : ''} />
      </div>
    </fieldset>
  );
}
