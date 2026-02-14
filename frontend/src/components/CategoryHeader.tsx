interface Props {
  name: string;
}

export default function CategoryHeader({ name }: Props) {
  return <div className="category-header">{name}</div>;
}
