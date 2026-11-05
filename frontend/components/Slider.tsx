type Props = {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (value: number) => void;
};

export function Slider({ label, hint, value, min, max, step, unit, onChange }: Props) {
  return (
    <label className="block text-sm">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="font-mono text-zinc-500">
          {value}
          {unit}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
      <span className="text-xs text-zinc-500">{hint}</span>
    </label>
  );
}
