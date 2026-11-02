import { axiosClient } from '#/lib/axiosClient'
import type {
  LabelInterval,
  Recording,
  RecordingDetail,
  TrainingJob,
  Rehearsal,
} from '#/features/calibration/types'

const base = '/api/calibration'

export const getRecordings = async (): Promise<Recording[]> =>
  (await axiosClient.get<Recording[]>(`${base}/recordings`)).data

export const getRecording = async (id: string): Promise<RecordingDetail> =>
  (await axiosClient.get<RecordingDetail>(`${base}/recordings/${id}`)).data

export const startRecording = async (body: {
  participant: string
  notes: string
  role: Recording['role']
}): Promise<Recording> =>
  (await axiosClient.post<Recording>(`${base}/recordings`, body)).data

export const stopRecording = async (id: string): Promise<Recording> =>
  (await axiosClient.post<Recording>(`${base}/recordings/${id}/stop`)).data

export const saveLabels = async (
  id: string,
  labels: LabelInterval[],
): Promise<void> => {
  await axiosClient.put(`${base}/recordings/${id}/labels`, labels)
}

export const getModels = async (): Promise<TrainingJob[]> =>
  (await axiosClient.get<TrainingJob[]>(`${base}/models`)).data

export const trainModel = async (recordingIds: string[]): Promise<void> => {
  await axiosClient.post(`${base}/training`, { recording_ids: recordingIds })
}

export const selectModel = async (id: string | null): Promise<void> => {
  await axiosClient.post(`${base}/selection`, { model_id: id })
}

export const getRehearsal = async (id: string): Promise<Rehearsal> =>
  (await axiosClient.get<Rehearsal>(`${base}/recordings/${id}/rehearsal`)).data
