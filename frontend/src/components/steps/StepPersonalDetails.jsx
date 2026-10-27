import FieldError from '../FieldError.jsx';

export default function StepPersonalDetails({ values, errors, touched, onChange, onBlur }) {
  return (
    <fieldset className="form-step">
      <legend>Personal Details</legend>

      <div className="form-field">
        <label htmlFor="full_name">Full name</label>
        <input
          id="full_name"
          name="full_name"
          type="text"
          value={values.full_name}
          onChange={(e) => onChange('full_name', e.target.value)}
          onBlur={() => onBlur('full_name')}
          aria-invalid={Boolean(touched.full_name && errors.full_name)}
        />
        <FieldError message={touched.full_name ? errors.full_name : ''} />
      </div>

      <div className="form-field">
        <label htmlFor="date_of_birth">Date of birth</label>
        <input
          id="date_of_birth"
          name="date_of_birth"
          type="date"
          value={values.date_of_birth}
          onChange={(e) => onChange('date_of_birth', e.target.value)}
          onBlur={() => onBlur('date_of_birth')}
          aria-invalid={Boolean(touched.date_of_birth && errors.date_of_birth)}
        />
        <FieldError message={touched.date_of_birth ? errors.date_of_birth : ''} />
      </div>

      <div className="form-field">
        <label htmlFor="id_number">ID number</label>
        <input
          id="id_number"
          name="id_number"
          type="text"
          value={values.id_number}
          onChange={(e) => onChange('id_number', e.target.value)}
          onBlur={() => onBlur('id_number')}
          aria-invalid={Boolean(touched.id_number && errors.id_number)}
        />
        <FieldError message={touched.id_number ? errors.id_number : ''} />
      </div>
    </fieldset>
  );
}
