import { useParams } from 'react-router-dom';
import { ConfigStudio } from '../configure/ConfigStudio';

export function ConfigFilePage() {
  const { name } = useParams();
  return <ConfigStudio mode="file" configName={name ?? null} allowConfigHistory />;
}
