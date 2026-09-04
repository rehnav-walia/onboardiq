import FieldError from '../FieldError.jsx';

export default function StepAddressContact({ values, errors, touched, onChange }) {
  return (
    <fieldset className="form-step">
      <legend>Address &amp; Contact</legend>

      <div className="form-field">
        <label htmlFor="address">Address</label>
        <textarea
          id="address"
          name="address"
          rows={3}
          value={values.address}
          onChange={(e) => onChange('address', e.target.value)}
          aria-invalid={Boolean(touched.address && errors.address)}
        />
        <FieldError message={touched.address ? errors.address : ''} />
      </div>

      <div className="form-field">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          value={values.email}
          onChange={(e) => onChange('email', e.target.value)}
          aria-invalid={Boolean(touched.email && errors.email)}
        />
        <FieldError message={touched.email ? errors.email : ''} />
      </div>

      <div className="form-field">
        <label htmlFor="phone">Phone</label>
        <input
          id="phone"
          name="phone"
          type="tel"
          value={values.phone}
          onChange={(e) => onChange('phone', e.target.value)}
          aria-invalid={Boolean(touched.phone && errors.phone)}
        />
        <FieldError message={touched.phone ? errors.phone : ''} />
      </div>
    </fieldset>
  );
}
